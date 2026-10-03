import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from fastapi.testclient import TestClient

from document_intelligence.api import create_app
from document_intelligence.api.rate_limit import RateLimiter
from document_intelligence.config import Settings
from document_intelligence.core.analysis import analyze_line_index, search_line_index
from document_intelligence.core.evidence import line_index_path
from document_intelligence.models import LineEvidence, LineIndex, PageEvidence
from document_intelligence.services import (
    QueryService,
    limit_evidence,
    parse_json_object,
)
from document_intelligence.sessions import SessionManager

from .test_api import FakeDocuments, FakeQueries


def make_index(name="report.pdf", pages=None) -> LineIndex:
    pages = pages or [
        ["Annual Report 2024", "Revenue grew 12.5% to $4,200,000.", "Contact a@b.com"],
        [],
        ["Item 10 20 30", "Item 11 21 31", "Item 12 22 32", "Item 13 23 33"],
    ]
    return LineIndex(
        doc_id="doc-1",
        name=name,
        source_path="/x.pdf",
        source_sha256="h",
        pages=[
            PageEvidence(
                page=number,
                lines=[
                    LineEvidence(line=i, text=t, bbox=[0, i, 10, i + 1])
                    for i, t in enumerate(texts, start=1)
                ],
            )
            for number, texts in enumerate(pages, start=1)
        ],
    )


class AnalysisTests(unittest.TestCase):
    def test_report(self) -> None:
        report = analyze_line_index(make_index())
        self.assertEqual(report.page_count, 3)
        self.assertEqual(report.likely_scanned_pages, [2])
        self.assertEqual(report.table_pages, [3])
        self.assertIn("a@b.com", report.entities["emails"])
        self.assertIn("12.5%", report.entities["percentages"])
        self.assertTrue(report.warnings)

    def test_fully_scanned_warns_ocr(self) -> None:
        report = analyze_line_index(make_index(pages=[[], []]))
        self.assertEqual(report.text_coverage, 0)
        self.assertIn("OCR", report.warnings[0])

    def test_search_ranks_phrase_first(self) -> None:
        hits = search_line_index(make_index(), "revenue grew")
        self.assertEqual(hits[0].citation.page, 1)
        self.assertEqual(hits[0].citation.start_line, 2)
        with self.assertRaises(ValueError):
            search_line_index(make_index(), "  ")


class ServiceHelperTests(unittest.TestCase):
    def test_parse_json_variants(self) -> None:
        self.assertEqual(parse_json_object('x {"a": 1} y'), {"a": 1})
        self.assertEqual(
            parse_json_object('```json\n{"a": {"b": 2}}\n```'), {"a": {"b": 2}}
        )
        self.assertEqual(parse_json_object('note {oops} {"ok": true}'), {"ok": True})
        with self.assertRaises(ValueError):
            parse_json_object("no json")

    def test_limit_evidence_keeps_first_page(self) -> None:
        index = make_index()
        pages, truncated = limit_evidence([index], {"report.pdf": [1, 3]}, 10)
        self.assertEqual(pages, {"report.pdf": [1]})
        self.assertTrue(truncated)
        pages, truncated = limit_evidence([index], {"report.pdf": [1, 3]}, 10_000)
        self.assertEqual(pages, {"report.pdf": [1, 3]})
        self.assertFalse(truncated)


class FakeAzure:
    def __init__(self, first: str, repaired: str):
        self.first, self.repaired, self.calls = first, repaired, []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.create))

    def create(self, **request):
        self.calls.append(request)
        if request["stream"]:
            chunk = SimpleNamespace(
                usage=None,
                choices=[SimpleNamespace(delta=SimpleNamespace(content=self.first))],
            )
            return iter([chunk])
        return SimpleNamespace(
            usage=None,
            choices=[SimpleNamespace(message=SimpleNamespace(content=self.repaired))],
        )


class RepairTests(unittest.TestCase):
    def build(self, first: str, repaired: str) -> Any:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        root = Path(self.temporary.name)
        settings = Settings(
            storage_path=root,
            upload_path=root / "u",
            azure_api_key="k",
            azure_endpoint="https://e",
            azure_api_version="v",
            index_model="i",
            chat_model="c",
            client_api_key="t",
        )
        destination = line_index_path(root, "doc-1")
        destination.parent.mkdir(parents=True)
        destination.write_text(make_index().model_dump_json())
        service: Any = object.__new__(QueryService)
        service.settings = settings
        service.client = SimpleNamespace(
            chat=lambda *a, **k: '<cite doc="report.pdf" page="1"/>'
        )
        service.azure = FakeAzure(first, repaired)
        return service

    def test_repairs_invalid_citation(self) -> None:
        good = 'Revenue grew. <cite doc="report.pdf" page="1" lines="2"/>'
        service = self.build('Bad <cite doc="report.pdf" page="1" lines="99"/>', good)
        result = service.ask(["doc-1"], "How did revenue change?")
        self.assertEqual(result.answer, good)
        self.assertEqual(result.citations[0].start_line, 2)
        self.assertEqual(len(service.azure.calls), 2)

    def test_unrepairable_raises(self) -> None:
        service = self.build("no cites", "still none")
        with self.assertRaises(ValueError):
            service.ask(["doc-1"], "How did revenue change?")


class HardeningTests(unittest.TestCase):
    def test_session_ttl_expires_idle_sessions(self) -> None:
        manager = SessionManager(ttl_seconds=1)
        session = manager.create(["a"])
        session.last_used = time.monotonic() - 5
        with self.assertRaises(KeyError):
            manager.get(session.id)

    def test_session_ttl_keeps_busy_sessions(self) -> None:
        manager = SessionManager(ttl_seconds=1)
        session = manager.create(["a"])
        manager.begin_message(session.id)
        session.last_used = time.monotonic() - 5
        self.assertIs(manager.get(session.id), session)

    def test_rate_limiter(self) -> None:
        limiter = RateLimiter(2)
        self.assertTrue(limiter.allow("c"))
        self.assertTrue(limiter.allow("c"))
        self.assertFalse(limiter.allow("c"))
        self.assertTrue(limiter.allow("other"))
        self.assertTrue(RateLimiter(0).allow("c"))


class InsightQueries(FakeQueries):
    def insights(self, document_ids, kind):
        from document_intelligence.models import StructuredExtraction

        return StructuredExtraction(schema_name=kind, data={"ok": True}, citations=[])


class AnalysisDocuments(FakeDocuments):
    def line_index(self, doc_id):
        if doc_id == "missing":
            raise ValueError("No local line index for missing.")
        return make_index()

    def analyze(self, doc_id):
        return analyze_line_index(self.line_index(doc_id))

    def search(self, doc_id, query, limit=20):
        return search_line_index(self.line_index(doc_id), query, limit)


class ApiFeatureTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        root = Path(self.temporary.name)
        settings = Settings(
            storage_path=root,
            upload_path=root / "u",
            azure_api_key="k",
            azure_endpoint="https://e",
            azure_api_version="v",
            index_model="i",
            chat_model="c",
            client_api_key="secret",
            rate_limit_per_minute=5,
        )
        app = create_app(settings, AnalysisDocuments(), InsightQueries())
        self.client = TestClient(app, headers={"Authorization": "Bearer secret"})

    def test_analysis_and_search(self) -> None:
        self.assertEqual(
            self.client.get("/documents/doc-1/analysis").json()["page_count"], 3
        )
        hits = self.client.get(
            "/documents/doc-1/search", params={"q": "revenue"}
        ).json()
        self.assertEqual(hits["hits"][0]["citation"]["page"], 1)

    def test_missing_index_is_404_and_bad_pages_422(self) -> None:
        self.assertEqual(
            self.client.get("/documents/missing/analysis").status_code, 404
        )
        self.assertEqual(self.client.get("/documents/doc-1/pages/abc").status_code, 422)
        self.assertEqual(self.client.get("/documents/doc-1/pages/99").status_code, 422)

    def test_insights(self) -> None:
        self.assertIn("risks", self.client.get("/insights").json()["kinds"])
        self.assertEqual(
            self.client.post("/documents/doc-1/insights/risks").json()["data"],
            {"ok": True},
        )
        self.assertEqual(
            self.client.post("/documents/doc-1/insights/nope").status_code, 404
        )

    def test_request_id_and_rate_limit(self) -> None:
        first = self.client.get("/documents", headers={"X-Request-ID": "abc"})
        self.assertEqual(first.headers["X-Request-ID"], "abc")
        statuses = [self.client.get("/documents").status_code for _ in range(6)]
        self.assertEqual(statuses[-1], 429)
        self.assertEqual(self.client.get("/health").status_code, 200)

    def test_ready(self) -> None:
        self.assertEqual(self.client.get("/health/ready").json(), {"status": "ready"})


if __name__ == "__main__":
    unittest.main()
