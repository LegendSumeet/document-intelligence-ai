import json
import shutil
import uuid
from hmac import compare_digest
from pathlib import Path
from typing import Annotated, Any

from fastapi import Depends, FastAPI, File, HTTPException, UploadFile, status
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from openai import OpenAIError
from pageindex import PageIndexAPIError
from pydantic import BaseModel, Field

from .citations import evidence_for_pages, parse_page_spec
from .config import Settings
from .services import DocumentService, QueryService
from .sessions import SessionManager


class QueryRequest(BaseModel):
    document_ids: list[str] = Field(min_length=1)
    question: str = Field(min_length=1)
    reasoning_effort: str | None = None


class ExtractionRequest(BaseModel):
    document_ids: list[str] = Field(min_length=1)
    instruction: str = Field(min_length=1)
    schema_name: str = "custom"


class SessionRequest(BaseModel):
    document_ids: list[str] = Field(min_length=1)


class MessageRequest(BaseModel):
    message: str = Field(min_length=1)
    reasoning_effort: str | None = None


def sse_event(event: str, data: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def create_app(
    settings: Settings | None = None,
    document_service: Any | None = None,
    query_service: Any | None = None,
    session_manager: SessionManager | None = None,
) -> FastAPI:
    settings = settings or Settings.from_env()
    documents = document_service or DocumentService(settings)
    queries = query_service or QueryService(settings, documents.client)
    sessions = session_manager or SessionManager()
    bearer = HTTPBearer(auto_error=False)

    def require_app_token(
        credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
    ) -> None:
        if credentials is None or not compare_digest(
            credentials.credentials, settings.client_api_key
        ):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or missing application token.",
                headers={"WWW-Authenticate": "Bearer"},
            )

    app = FastAPI(
        title="Document Intelligence API",
        version="0.3.0",
        dependencies=[Depends(require_app_token)],
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.cors_origins),
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type", "Authorization"],
    )

    async def validate_document_ids(document_ids: list[str]) -> None:
        for document_id in dict.fromkeys(document_ids):
            try:
                document = await run_in_threadpool(documents.info, document_id)
            except (PageIndexAPIError, ValueError) as error:
                raise HTTPException(
                    404, f"Document not found: {document_id}"
                ) from error
            if document.get("status") != "completed" or not document.get(
                "retrievalReady", False
            ):
                raise HTTPException(409, f"Document is not ready: {document_id}")

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/documents")
    async def upload_document(file: Annotated[UploadFile, File()]):
        if not file.filename or not file.filename.lower().endswith(".pdf"):
            raise HTTPException(415, "Only PDF uploads are supported.")
        upload_directory = settings.upload_path / str(uuid.uuid4())
        upload_directory.mkdir(parents=True)
        upload_path = upload_directory / Path(file.filename).name
        try:
            with upload_path.open("wb") as destination:
                total = 0
                while chunk := await file.read(1024 * 1024):
                    total += len(chunk)
                    if total > settings.max_upload_bytes:
                        raise HTTPException(
                            413, "Upload exceeds the configured size limit."
                        )
                    destination.write(chunk)
            result = await run_in_threadpool(documents.index, str(upload_path))
            return result.model_dump()
        except (PageIndexAPIError, ValueError) as error:
            shutil.rmtree(upload_directory, ignore_errors=True)
            raise HTTPException(422, str(error)) from error
        except Exception:
            shutil.rmtree(upload_directory, ignore_errors=True)
            raise
        finally:
            await file.close()

    @app.get("/documents")
    async def list_documents():
        return {"documents": await run_in_threadpool(documents.list)}

    @app.get("/documents/{doc_id}")
    async def get_document(doc_id: str):
        return await run_in_threadpool(documents.info, doc_id)

    @app.get("/documents/{doc_id}/structure")
    async def get_structure(doc_id: str):
        return await run_in_threadpool(documents.structure, doc_id)

    @app.get("/documents/{doc_id}/pages/{page_spec}")
    async def get_pages(doc_id: str, page_spec: str):
        index = await run_in_threadpool(documents.line_index, doc_id)
        pages = parse_page_spec(page_spec)
        return {
            "document": doc_id,
            "pages": pages,
            "evidence": evidence_for_pages(index, pages),
        }

    @app.get("/documents/{doc_id}/evidence/{page_number}")
    async def get_evidence(doc_id: str, page_number: int):
        index = await run_in_threadpool(documents.line_index, doc_id)
        page = next((item for item in index.pages if item.page == page_number), None)
        if page is None:
            raise HTTPException(404, "Evidence page not found.")
        return {"document": index.name, "doc_id": doc_id, **page.model_dump()}

    @app.get("/documents/{doc_id}/file")
    async def get_document_file(doc_id: str):
        index = await run_in_threadpool(documents.line_index, doc_id)
        source = Path(index.source_path)
        if not source.is_file():
            raise HTTPException(404, "Source PDF is no longer available locally.")
        return FileResponse(source, media_type="application/pdf", filename=index.name)

    @app.post("/queries")
    async def query(request: QueryRequest):
        try:
            result = await run_in_threadpool(
                queries.ask,
                request.document_ids,
                request.question,
                request.reasoning_effort,
            )
            return result.model_dump()
        except (ValueError, TypeError) as error:
            raise HTTPException(422, str(error)) from error

    @app.post("/extractions")
    async def extract(request: ExtractionRequest):
        try:
            result = await run_in_threadpool(
                queries.extract,
                request.document_ids,
                request.instruction,
                request.schema_name,
            )
            return result.model_dump()
        except (ValueError, TypeError) as error:
            raise HTTPException(422, str(error)) from error

    @app.post("/chat/sessions", status_code=201)
    async def create_session(request: SessionRequest):
        await validate_document_ids(request.document_ids)
        return sessions.create(request.document_ids).public()

    @app.get("/chat/sessions/{session_id}")
    def get_session(session_id: str):
        try:
            return sessions.get(session_id).public()
        except KeyError as error:
            raise HTTPException(404, "Chat session not found.") from error

    @app.put("/chat/sessions/{session_id}/documents")
    async def update_session_documents(session_id: str, request: SessionRequest):
        try:
            await validate_document_ids(request.document_ids)
            return sessions.update_documents(session_id, request.document_ids).public()
        except KeyError as error:
            raise HTTPException(404, "Chat session not found.") from error
        except RuntimeError as error:
            raise HTTPException(409, str(error)) from error

    @app.delete("/chat/sessions/{session_id}", status_code=204)
    def delete_session(session_id: str):
        try:
            sessions.delete(session_id)
        except KeyError as error:
            raise HTTPException(404, "Chat session not found.") from error

    @app.post("/chat/sessions/{session_id}/messages")
    async def send_message(session_id: str, request: MessageRequest):
        try:
            document_ids, history = sessions.begin_message(session_id)
        except KeyError as error:
            raise HTTPException(404, "Chat session not found.") from error
        except RuntimeError as error:
            raise HTTPException(409, str(error)) from error
        try:
            result = await run_in_threadpool(
                queries.ask,
                document_ids,
                request.message,
                request.reasoning_effort,
                history,
            )
            sessions.complete_message(session_id, request.message, result.answer)
            return result.model_dump()
        except (ValueError, TypeError) as error:
            sessions.fail_message(session_id)
            raise HTTPException(422, str(error)) from error
        except Exception:
            sessions.fail_message(session_id)
            raise

    @app.post("/chat/sessions/{session_id}/messages/stream")
    def stream_message(session_id: str, request: MessageRequest):
        try:
            document_ids, history = sessions.begin_message(session_id)
        except KeyError as error:
            raise HTTPException(404, "Chat session not found.") from error
        except RuntimeError as error:
            raise HTTPException(409, str(error)) from error

        def events():
            completed = False
            try:
                for event in queries.stream(
                    document_ids,
                    request.message,
                    request.reasoning_effort,
                    history,
                ):
                    payload = event.model_dump(exclude_none=True)
                    yield sse_event(event.type, payload)
                    if event.type == "complete":
                        answer = event.data.get("answer", "")
                        sessions.complete_message(session_id, request.message, answer)
                        completed = True
            except (OpenAIError, PageIndexAPIError, TypeError, ValueError) as error:
                yield sse_event(
                    "error",
                    {"type": "error", "stage": "error", "message": str(error)},
                )
            finally:
                if not completed:
                    sessions.fail_message(session_id)

        return StreamingResponse(
            events(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache, no-transform",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    return app


app = create_app()
