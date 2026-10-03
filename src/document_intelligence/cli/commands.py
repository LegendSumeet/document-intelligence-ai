import argparse
import json
import os
from collections.abc import Iterator
from typing import Protocol

from pageindex import PageIndexAPIError

from ..config import Settings
from ..core.citations import evidence_for_pages, parse_page_spec
from ..models import QueryEvent, QueryResult
from ..services import INSIGHT_PRESETS, DocumentService, QueryService


def print_json(value) -> None:
    if hasattr(value, "model_dump"):
        value = value.model_dump()
    print(json.dumps(value, indent=2, ensure_ascii=False))


class StreamingQueryService(Protocol):
    def stream(
        self,
        doc_ids: list[str],
        question: str,
        reasoning_effort: str | None,
        history: list[dict[str, str]],
    ) -> Iterator[QueryEvent]: ...


def parse_document_selection(selection: str, document_count: int) -> list[int]:
    if selection.strip().lower() == "all":
        return list(range(document_count))
    indexes = []
    for value in selection.split(","):
        try:
            index = int(value.strip()) - 1
        except ValueError as error:
            raise ValueError(
                "Select documents by number, separated by commas."
            ) from error
        if index < 0 or index >= document_count:
            raise ValueError(f"Document selection is out of range: {index + 1}")
        if index not in indexes:
            indexes.append(index)
    if not indexes:
        raise ValueError("Select at least one document.")
    return indexes


def print_document_menu(documents: list[dict]) -> None:
    print("\nAvailable documents:")
    for number, document in enumerate(documents, start=1):
        print(
            f"  {number}. {document['name']} "
            f"({document.get('pageNum', '?')} pages, {document['status']})"
        )


def choose_documents(documents: list[dict]) -> list[dict]:
    if not documents:
        raise ValueError("No indexed documents found. Run the index command first.")
    while True:
        print_document_menu(documents)
        selection = input(
            "Select document number(s), comma-separated, or 'all': "
        ).strip()
        try:
            return [
                documents[index]
                for index in parse_document_selection(selection, len(documents))
            ]
        except ValueError as error:
            print(f"Error: {error}")


def stream_answer(
    query_service: StreamingQueryService,
    doc_ids: list[str],
    question: str,
    reasoning_effort: str | None,
    history: list[dict[str, str]],
    show_process: bool,
) -> QueryResult:
    result = None
    answer_started = False
    for event in query_service.stream(doc_ids, question, reasoning_effort, history):
        if event.type == "status":
            if show_process:
                print(f"[{event.stage}] {event.message}")
                if event.stage == "evidence":
                    selected = event.data.get("selected_pages", {})
                    for name, pages in selected.items():
                        print(f"  - {name}: pages {', '.join(map(str, pages))}")
        elif event.type == "answer_delta" and event.delta:
            if not answer_started:
                print("\nassistant [draft]> ", end="", flush=True)
                answer_started = True
            print(event.delta, end="", flush=True)
        elif event.type == "validation":
            if answer_started:
                print()
            print(f"[verified] {event.message}")
        elif event.type == "complete":
            result = QueryResult.model_validate(event.data)
    if result is None:
        raise ValueError("The streamed query completed without a result.")
    return result


def interactive_chat(
    settings: Settings,
    documents: DocumentService,
    reasoning_effort: str | None,
    show_process: bool,
) -> None:
    available = documents.list()
    selected = choose_documents(available)
    query_service = QueryService(settings, documents.client)
    history: list[dict[str, str]] = []

    print("\nSelected: " + ", ".join(document["name"] for document in selected))
    print("Ask a question, or use: docs, use, help, exit")
    while True:
        try:
            question = input("\nyou> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nSession ended.")
            return
        if not question:
            continue
        command = question.lower()
        if command in {"exit", "quit", "/exit", "/quit"}:
            print("Session ended.")
            return
        if command in {"docs", "/docs"}:
            print("Selected: " + ", ".join(document["name"] for document in selected))
            continue
        if command in {"use", "/use"}:
            selected = choose_documents(available)
            print("Selected: " + ", ".join(document["name"] for document in selected))
            continue
        if command in {"help", "/help"}:
            print("docs: show selection | use: change selection | exit: end session")
            continue

        try:
            result = stream_answer(
                query_service,
                [document["id"] for document in selected],
                question,
                reasoning_effort,
                history,
                show_process,
            )
            history.extend(
                [
                    {"role": "user", "content": question},
                    {"role": "assistant", "content": result.answer},
                ]
            )
        except (PageIndexAPIError, TypeError, ValueError) as error:
            print(f"\n[error] {error}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Local document intelligence with PageIndex and verified citations."
    )
    parser.add_argument(
        "--storage-path",
        default=os.getenv("PAGEINDEX_STORAGE_PATH", ".pageindex"),
    )
    commands = parser.add_subparsers(dest="command", required=True)
    index = commands.add_parser("index")
    index.add_argument("pdf")
    index.add_argument("--force", action="store_true")
    ask = commands.add_parser("ask")
    ask.add_argument("doc_id")
    ask.add_argument("question")
    ask.add_argument("--with-doc", action="append", default=[], metavar="DOC_ID")
    ask.add_argument("--reasoning-effort", choices=("low", "medium", "high"))
    ask.add_argument("--show-process", action="store_true")
    ask.add_argument("--json", action="store_true")
    ask.add_argument("--page-citations", action="store_true")
    chat = commands.add_parser(
        "chat", help="Select documents and start an interactive chat."
    )
    chat.add_argument("--reasoning-effort", choices=("low", "medium", "high"))
    chat.add_argument("--show-process", action="store_true", default=True)
    chat.add_argument(
        "--quiet-process",
        action="store_false",
        dest="show_process",
        help="Hide retrieval stages while continuing to stream the answer.",
    )
    extract = commands.add_parser("extract")
    extract.add_argument("doc_id")
    extract.add_argument("instruction")
    extract.add_argument("--with-doc", action="append", default=[], metavar="DOC_ID")
    extract.add_argument("--schema-name", default="custom")
    for name in ("info", "structure"):
        command = commands.add_parser(name)
        command.add_argument("doc_id")
    analyze = commands.add_parser("analyze", help="Deterministic document analysis.")
    analyze.add_argument("doc_id")
    search = commands.add_parser("search", help="Keyword search with line citations.")
    search.add_argument("doc_id")
    search.add_argument("query")
    search.add_argument("--limit", type=int, default=10)
    insights = commands.add_parser("insights", help="AI insight preset with citations.")
    insights.add_argument("doc_id")
    insights.add_argument("kind", choices=tuple(INSIGHT_PRESETS))
    pages = commands.add_parser("pages")
    pages.add_argument("doc_id")
    pages.add_argument("pages")
    commands.add_parser("list")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        settings = Settings.from_env(args.storage_path)
        documents = DocumentService(settings)
        if args.command == "index":
            result = documents.index(args.pdf, args.force)
            label = "Already indexed as" if result.reused else "Indexed"
            print(f"{label} {result.document.name}")
            print(f"Document ID: {result.document.doc_id}")
            print("Local line index: ready")
        elif args.command == "list":
            items = documents.list()
            if not items:
                print("No indexed documents found.")
            for item in items:
                print(
                    f"{item['id']}  {item['name']}  {item['status']}  "
                    f"{item.get('pageNum', '?')} pages"
                )
        elif args.command == "info":
            print_json(documents.info(args.doc_id))
        elif args.command == "structure":
            print_json(documents.structure(args.doc_id))
        elif args.command == "analyze":
            print_json(documents.analyze(args.doc_id))
        elif args.command == "search":
            for hit in documents.search(args.doc_id, args.query, args.limit):
                c = hit.citation
                print(f"[{hit.score}] p{c.page} L{c.start_line}: {c.text}")
        elif args.command == "insights":
            print_json(
                QueryService(settings, documents.client).insights(
                    [args.doc_id], args.kind
                )
            )
        elif args.command == "pages":
            index = documents.line_index(args.doc_id)
            print(evidence_for_pages(index, parse_page_spec(args.pages)))
        elif args.command == "ask":
            doc_ids = [args.doc_id, *args.with_doc]
            if args.page_citations:
                stream = documents.client.chat(
                    args.question,
                    doc_id=doc_ids[0] if len(doc_ids) == 1 else doc_ids,
                    stream=True,
                    reasoning_effort=args.reasoning_effort,
                    show_process=args.show_process,
                )
                for chunk in stream:
                    print(chunk, end="", flush=True)
                print()
            else:
                result = QueryService(settings, documents.client).ask(
                    doc_ids, args.question, args.reasoning_effort
                )
                if args.show_process:
                    selection = "; ".join(
                        f"{name}: {', '.join(map(str, pages))}"
                        for name, pages in result.selected_pages.items()
                    )
                    print(f"[evidence] selected pages: {selection}")
                print_json(result) if args.json else print(result.answer)
        elif args.command == "chat":
            interactive_chat(
                settings, documents, args.reasoning_effort, args.show_process
            )
        elif args.command == "extract":
            result = QueryService(settings, documents.client).extract(
                [args.doc_id, *args.with_doc], args.instruction, args.schema_name
            )
            print_json(result)
    except (
        FileNotFoundError,
        KeyError,
        PageIndexAPIError,
        TypeError,
        ValueError,
    ) as error:
        print(f"Error: {error}")
        return 1
    return 0
