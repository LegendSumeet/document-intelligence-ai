import io
import unittest
from contextlib import redirect_stdout

from document_intelligence.citations import parse_page_spec, validate_line_citations
from document_intelligence.cli import parse_document_selection, stream_answer
from document_intelligence.models import QueryEvent


def line_index(doc_id: str, name: str, lines: list[str]) -> dict:
    return {
        "doc_id": doc_id,
        "name": name,
        "source_path": f"/documents/{name}",
        "source_sha256": "test-hash",
        "pages": [
            {
                "page": 1,
                "lines": [
                    {"line": number, "text": text, "bbox": [0, number, 10, number + 1]}
                    for number, text in enumerate(lines, start=1)
                ],
            }
        ],
    }


class PageSpecTests(unittest.TestCase):
    def test_expands_and_deduplicates_ranges(self) -> None:
        self.assertEqual(parse_page_spec("1-3,2,5"), [1, 2, 3, 5])

    def test_rejects_reversed_range(self) -> None:
        with self.assertRaisesRegex(ValueError, "Invalid page selection"):
            parse_page_spec("4-2")


class DocumentSelectionTests(unittest.TestCase):
    def test_selects_multiple_documents_without_duplicates(self) -> None:
        self.assertEqual(parse_document_selection("2, 1, 2", 3), [1, 0])

    def test_selects_all_documents(self) -> None:
        self.assertEqual(parse_document_selection("all", 3), [0, 1, 2])

    def test_rejects_out_of_range_selection(self) -> None:
        with self.assertRaisesRegex(ValueError, "out of range"):
            parse_document_selection("4", 3)


class StreamingChatTests(unittest.TestCase):
    def test_renders_process_deltas_and_verification(self) -> None:
        class FakeQueryService:
            def stream(self, doc_ids, question, reasoning_effort, history):
                yield QueryEvent(
                    type="status", stage="retrieval", message="Searching tree."
                )
                yield QueryEvent(
                    type="answer_delta", stage="generation", delta="Hello "
                )
                yield QueryEvent(
                    type="answer_delta", stage="generation", delta="world."
                )
                yield QueryEvent(
                    type="validation",
                    stage="validation",
                    message="Verified 1 citation.",
                )
                yield QueryEvent(
                    type="complete",
                    stage="complete",
                    data={
                        "query_id": "query-1",
                        "answer": "Hello world.",
                        "documents": doc_ids,
                        "selected_pages": {"report.pdf": [1]},
                        "citations": [],
                        "verification_status": "location_verified",
                        "usage": {},
                    },
                )

        output = io.StringIO()
        with redirect_stdout(output):
            result = stream_answer(
                FakeQueryService(), ["doc-1"], "Question", None, [], True
            )

        rendered = output.getvalue()
        self.assertIn("[retrieval] Searching tree.", rendered)
        self.assertIn("assistant [draft]> Hello world.", rendered)
        self.assertIn("[verified] Verified 1 citation.", rendered)
        self.assertEqual(result.answer, "Hello world.")


class ConversationalRoutingTests(unittest.TestCase):
    def test_routes_greeting_without_document_retrieval(self) -> None:
        from document_intelligence.services import QueryService

        answer = QueryService._conversational_answer("  Hey ")
        self.assertIn("Hello", answer or "")

    def test_keeps_document_question_for_retrieval(self) -> None:
        from document_intelligence.services import QueryService

        self.assertIsNone(QueryService._conversational_answer("Explain clause 4.2"))


class CitationValidationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.first = line_index("doc-1", "first.pdf", ["Alpha", "Beta"])
        self.second = line_index("doc-2", "second.pdf", ["Gamma", "Delta"])
        self.selected = {"first.pdf": [1], "second.pdf": [1]}

    def test_resolves_multi_document_evidence(self) -> None:
        answer = (
            'A <cite doc="first.pdf" page="1" lines="1-2"/> '
            'B <cite doc="second.pdf" page="1" lines="2"/>'
        )

        citations = validate_line_citations(
            answer, [self.first, self.second], self.selected
        )

        self.assertEqual(citations[0]["text"], "Alpha\nBeta")
        self.assertEqual(citations[1]["doc_id"], "doc-2")
        self.assertEqual(citations[1]["bounding_boxes"], [[0, 2, 10, 3]])

    def test_rejects_page_not_supplied_to_model(self) -> None:
        answer = '<cite doc="first.pdf" page="1" lines="1"/>'

        with self.assertRaisesRegex(ValueError, "outside the supplied evidence"):
            validate_line_citations(answer, [self.first], {"first.pdf": []})

    def test_rejects_unknown_document(self) -> None:
        answer = '<cite doc="invented.pdf" page="1" lines="1"/>'

        with self.assertRaisesRegex(ValueError, "unknown document"):
            validate_line_citations(answer, [self.first], self.selected)

    def test_rejects_out_of_range_lines(self) -> None:
        answer = '<cite doc="first.pdf" page="1" lines="2-9"/>'

        with self.assertRaisesRegex(ValueError, "outside the source"):
            validate_line_citations(answer, [self.first], self.selected)


if __name__ == "__main__":
    unittest.main()
