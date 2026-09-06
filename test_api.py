import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient
from pageindex import PageIndexAPIError

from document_intelligence.api import create_app
from document_intelligence.config import Settings
from document_intelligence.models import (
    Citation,
    IndexResult,
    LineEvidence,
    LineIndex,
    PageEvidence,
    QueryEvent,
    QueryResult,
)


class FakeDocuments:
    client = object()

    def list(self):
        return [{"id": "doc-1", "name": "report.pdf", "status": "completed"}]

    def info(self, doc_id):
        return {"id": doc_id, "status": "completed", "retrievalReady": True}

    def index(self, file_path):
        from document_intelligence.models import DocumentRecord

        path = Path(file_path)
        return IndexResult(
            document=DocumentRecord(
                doc_id="doc-1",
                name=path.name,
                source_path=str(path),
                source_sha256="hash",
                status="completed",
                page_count=1,
            ),
            reused=False,
        )

    def structure(self, doc_id):
        return [{"node_id": "0001", "title": "Overview", "page_index": 1}]

    def line_index(self, doc_id):
        return LineIndex(
            doc_id=doc_id,
            name="report.pdf",
            source_path="/documents/report.pdf",
            source_sha256="hash",
            pages=[
                PageEvidence(
                    page=1,
                    lines=[LineEvidence(line=1, text="Evidence", bbox=[0, 0, 10, 10])],
                )
            ],
        )


class FakeQueries:
    def ask(self, document_ids, question, reasoning_effort=None, history=None):
        return QueryResult(
            query_id="query-1",
            answer="Supported answer.",
            documents=document_ids,
            selected_pages={"report.pdf": [1]},
            citations=[
                Citation(
                    document="report.pdf",
                    doc_id="doc-1",
                    page=1,
                    start_line=1,
                    end_line=1,
                    text="Evidence",
                    bounding_boxes=[[0, 0, 10, 10]],
                )
            ],
            verification_status="location_verified",
        )

    def stream(self, document_ids, question, reasoning_effort=None, history=None):
        yield QueryEvent(type="status", stage="retrieval", message="Searching.")
        yield QueryEvent(type="answer_delta", stage="generation", delta="Supported ")
        yield QueryEvent(type="answer_delta", stage="generation", delta="answer.")
        yield QueryEvent(
            type="validation", stage="validation", message="Verified 1 citation."
        )
        yield QueryEvent(
            type="complete",
            stage="complete",
            data=self.ask(
                document_ids, question, reasoning_effort, history
            ).model_dump(),
        )


class RejectingDocuments(FakeDocuments):
    def index(self, file_path):
        raise PageIndexAPIError(
            "Failed to submit document: PDF has no content. All pages are blank."
        )


class ApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        root = Path(self.temporary.name)
        self.settings = Settings(
            storage_path=root,
            upload_path=root / "uploads",
            azure_api_key="key",
            azure_endpoint="https://example.openai.azure.com",
            azure_api_version="2024-10-21",
            index_model="index",
            chat_model="chat",
            client_api_key="flutter-test-key",
        )
        app = create_app(self.settings, FakeDocuments(), FakeQueries())
        self.client = TestClient(
            app, headers={"Authorization": "Bearer flutter-test-key"}
        )

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_health(self) -> None:
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})

    def test_rejects_missing_app_token(self) -> None:
        response = TestClient(self.client.app).get("/health")
        self.assertEqual(response.status_code, 401)

    def test_query_returns_resolved_citations(self) -> None:
        response = self.client.post(
            "/queries",
            json={"document_ids": ["doc-1"], "question": "What happened?"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["verification_status"], "location_verified")
        self.assertEqual(response.json()["citations"][0]["text"], "Evidence")

    def test_upload_rejects_non_pdf(self) -> None:
        response = self.client.post(
            "/documents", files={"file": ("notes.txt", b"text", "text/plain")}
        )
        self.assertEqual(response.status_code, 415)

    def test_upload_preserves_filename(self) -> None:
        response = self.client.post(
            "/documents",
            files={"file": ("annual-report.pdf", b"%PDF-1.7", "application/pdf")},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["document"]["name"], "annual-report.pdf")

    def test_upload_returns_actionable_error_for_blank_pdf(self) -> None:
        app = create_app(
            self.settings,
            RejectingDocuments(),
            FakeQueries(),
        )
        client = TestClient(app, headers={"Authorization": "Bearer flutter-test-key"})

        response = client.post(
            "/documents",
            files={"file": ("blank.pdf", b"%PDF-1.7", "application/pdf")},
        )

        self.assertEqual(response.status_code, 422)
        self.assertIn("PDF has no content", response.json()["detail"])

    def test_evidence_returns_lines_and_bounding_boxes(self) -> None:
        response = self.client.get("/documents/doc-1/evidence/1")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["lines"][0]["text"], "Evidence")
        self.assertEqual(response.json()["lines"][0]["bbox"], [0.0, 0.0, 10.0, 10.0])

    def test_chat_session_lifecycle(self) -> None:
        created = self.client.post("/chat/sessions", json={"document_ids": ["doc-1"]})
        self.assertEqual(created.status_code, 201)
        session_id = created.json()["id"]

        message = self.client.post(
            f"/chat/sessions/{session_id}/messages",
            json={"message": "What happened?"},
        )
        self.assertEqual(message.status_code, 200)

        session = self.client.get(f"/chat/sessions/{session_id}").json()
        self.assertEqual(len(session["history"]), 2)
        self.assertFalse(session["busy"])

        deleted = self.client.delete(f"/chat/sessions/{session_id}")
        self.assertEqual(deleted.status_code, 204)
        self.assertEqual(
            self.client.get(f"/chat/sessions/{session_id}").status_code, 404
        )

    def test_chat_stream_returns_ordered_sse_events(self) -> None:
        session_id = self.client.post(
            "/chat/sessions", json={"document_ids": ["doc-1"]}
        ).json()["id"]

        response = self.client.post(
            f"/chat/sessions/{session_id}/messages/stream",
            json={"message": "What happened?"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.headers["content-type"], "text/event-stream; charset=utf-8"
        )
        self.assertLess(
            response.text.index("event: status"),
            response.text.index("event: answer_delta"),
        )
        self.assertLess(
            response.text.index("event: validation"),
            response.text.index("event: complete"),
        )


if __name__ == "__main__":
    unittest.main()
