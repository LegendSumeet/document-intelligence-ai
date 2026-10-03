import builtins
from pathlib import Path
from typing import Any

from pageindex import PageIndexClient

from ..config import Settings
from ..core.analysis import analyze_line_index, search_line_index
from ..core.evidence import build_line_index, file_sha256, load_line_index
from ..models import (
    AnalysisReport,
    DocumentRecord,
    IndexResult,
    SearchHit,
)
from ..providers import create_pageindex_client


class DocumentService:
    def __init__(self, settings: Settings, client: PageIndexClient | None = None):
        self.settings = settings
        self.settings.ensure_directories()
        self.client = client or create_pageindex_client(settings)

    def index(self, file_path: str, force: bool = False) -> IndexResult:
        document = Path(file_path).expanduser().resolve()
        if not document.is_file():
            raise FileNotFoundError(f"PDF not found: {document}")
        if document.suffix.lower() != ".pdf":
            raise ValueError("PageIndex Flash currently accepts PDF files only.")
        source_hash = file_sha256(document)
        existing = None if force else self._find_existing(str(document), source_hash)
        if existing:
            line_index = build_line_index(
                document, self.settings.storage_path, existing["id"], existing["name"]
            )
            return IndexResult(
                document=self._record(existing, line_index.source_path, source_hash),
                reused=True,
            )
        result = self.client.submit_document(
            str(document),
            metadata={"source_path": str(document), "source_sha256": source_hash},
        )
        metadata = self.client.get_document(result["doc_id"])
        build_line_index(
            document, self.settings.storage_path, result["doc_id"], result["name"]
        )
        return IndexResult(
            document=self._record(metadata, str(document), source_hash), reused=False
        )

    def list(self) -> list[dict[str, Any]]:
        return self.client.list_documents(limit=100).get("documents", [])

    def info(self, doc_id: str) -> dict[str, Any]:
        document = self.client.get_document(doc_id)
        document["retrievalReady"] = self.client.is_retrieval_ready(doc_id)
        return document

    def structure(self, doc_id: str) -> builtins.list[dict[str, Any]]:
        return self.client.get_document_structure(doc_id)

    def line_index(self, doc_id: str):
        return load_line_index(self.settings.storage_path, doc_id)

    def analyze(self, doc_id: str) -> AnalysisReport:
        return analyze_line_index(self.line_index(doc_id))

    def search(
        self, doc_id: str, query: str, limit: int = 20
    ) -> builtins.list[SearchHit]:
        return search_line_index(self.line_index(doc_id), query, limit)

    def _find_existing(self, source_path: str, source_hash: str) -> dict | None:
        for document in self.list():
            metadata = document.get("metadata") or {}
            if metadata.get("source_path") == source_path:
                return document
            if metadata.get("source_sha256") == source_hash:
                return document
        return None

    @staticmethod
    def _record(
        metadata: dict[str, Any], source_path: str, source_hash: str
    ) -> DocumentRecord:
        return DocumentRecord(
            doc_id=metadata.get("id") or metadata["doc_id"],
            name=metadata["name"],
            source_path=source_path,
            source_sha256=source_hash,
            status=metadata.get("status", "completed"),
            page_count=metadata.get("pageNum", 0),
        )
