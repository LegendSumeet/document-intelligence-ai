# Document Intelligence with PageIndex Flash

This project uses `PageIndexClient` in local mode with Gemini. PageIndex
Flash builds a hierarchical tree from a PDF's existing text and layout. A local
PyMuPDF evidence index adds numbered lines and bounding boxes for verified
line-level citations without PageIndex Cloud.

Flash is the default local indexer in `pageindex>=0.2.14`; there is no separate
Flash client or flag.

The application is organized as a reusable `document_intelligence` package with
both CLI and FastAPI interfaces. See [IMPLEMENTATION.md](IMPLEMENTATION.md) for
architecture, guarantees, API contracts, and the production roadmap.
See [FEATURES.md](FEATURES.md) for the complete feature inventory and status of
implemented, partial, planned, and deferred capabilities.
See [FLUTTER_API.md](FLUTTER_API.md) for the mobile session lifecycle, endpoint
payloads, SSE event format, emulator URLs, and citation highlighting data.

## Setup

Install the locked dependencies:

```bash
uv sync
```

Run the test suite:

```bash
uv run pytest -q
```

Create a `.env` file containing:

```dotenv
GEMINI_API_KEY=...
DOCUMENT_INTELLIGENCE_API_KEY=...
```

The app uses `gemini-3.8-flash` for both indexing and chat.

## Usage

Index a PDF once:

```bash
uv run document-intelligence index samples/test.pdf
```

Running the same command again reuses the existing document ID. Use `--force`
only when the PDF changed and you intentionally want a new index:

```bash
uv run document-intelligence index samples/test.pdf --force
```

Save the returned document ID, then reuse the persisted index for questions:

```bash
uv run document-intelligence ask DOC_ID "Tell me about Sumeet Vishwakarma"
```

By default, `ask` first uses PageIndex to select relevant pages, then asks Gemini
OpenAI to answer only from locally numbered evidence. It validates that every
result contains citations whose document, page, and line ranges exist:

```text
Sumeet is a founding engineer. <cite doc="test_1.pdf" page="1" lines="16-18"/>
```

Useful options:

```bash
uv run document-intelligence list
uv run document-intelligence info DOC_ID
uv run document-intelligence structure DOC_ID
uv run document-intelligence pages DOC_ID "1-2"
uv run document-intelligence ask DOC_ID "Summarize the document" --reasoning-effort high
uv run document-intelligence ask DOC_ID "Summarize the document" --show-process
uv run document-intelligence ask DOC_ID "Summarize the document" --json
uv run document-intelligence ask DOC_ID "Summarize the document" --page-citations
uv run document-intelligence extract DOC_ID "Extract education and work history"
uv run document-intelligence chat --show-process
```

The interactive `chat` command lists indexed documents first. Select one or
multiple documents by number, then ask questions against that fixed scope. Use
`docs` to view the current selection, `use` to change it, and `exit` to finish.
Each question displays document scoping, PageIndex tree retrieval, selected
evidence pages, grounded generation, and citation validation. Answer tokens are
streamed as Markdown source drafts and marked verified only after all citations
pass. Recent turns are kept in memory for follow-up questions. Use
`--quiet-process` to hide stage messages while retaining answer streaming.

Compare or synthesize across documents by repeating `--with-doc`:

```bash
uv run document-intelligence ask DOC_ID "Compare the candidates' experience" \
	--with-doc ANOTHER_DOC_ID
```

Multi-document answers retain verified line citations. `--json` resolves each
citation to its document ID, exact text, and PDF bounding boxes, making the
result suitable for an API response or a source-highlighting interface.

## API

Start the local API:

```bash
uv run uvicorn document_intelligence.api:create_app --factory --reload
```

Open `http://127.0.0.1:8000/docs` for the interactive OpenAPI interface. The API
supports PDF upload, document listing and inspection, verified queries, and
structured extraction. Indexing is synchronous in this phase; durable jobs and
application storage are intentionally deferred.

`structure` is the cheapest way to inspect what PageIndex indexed. `pages` shows
the exact numbered source lines used by the grounded answer.

Indexes are stored in `.pageindex/` by default. Override that location with
`--storage-path` or the `PAGEINDEX_STORAGE_PATH` environment variable.

## Choosing Local or Cloud

Use local PageIndex Flash for text-based PDFs with a selectable text layer. It
runs on your machine and persists indexes locally. This project adds validated
line references over that local text. It does not perform OCR or image
understanding.

Use PageIndex Cloud (`index="cloud"`) for scanned PDFs, image-heavy reports,
line-level citations, managed storage, or large multi-document collections.

The local citation validator proves that each cited location exists. It does not
mathematically prove that the cited text entails every generated claim. Keep the
numbered evidence available for human review in high-stakes workflows.

## Further Extensions

The SDK also supports multi-turn conversations, machine-readable streaming
events, OpenAI/Anthropic agent-tool adapters, full OCR export, and document
deletion. Those are best added when the application has a session store, an
event consumer, an agent framework, or an explicit confirmation flow rather
than exposing them as loosely connected commands.

## Analysis, search and insights

Deterministic (no model calls):

```bash
uv run document-intelligence analyze <doc_id>        # stats, scanned pages, tables, entities, warnings
uv run document-intelligence search <doc_id> "term"  # ranked hits with page/line/bbox citations
```

AI insights with verified citations (`summary`, `key_facts`, `risks`, `obligations`, `action_items`):

```bash
uv run document-intelligence insights <doc_id> risks
```

HTTP: `GET /documents/{id}/analysis`, `GET /documents/{id}/search?q=`,
`GET /insights`, `POST /documents/{id}/insights/{kind}`, `GET /health/ready`.

## Reliability behavior

- Invalid citations trigger one automatic repair attempt before the query fails.
- Evidence is trimmed to `DOCUMENT_INTELLIGENCE_MAX_EVIDENCE_CHARS`; the `evidence` stream event reports `truncated`.
- Gemini calls use configurable timeout/retries; provider failures return 502 instead of 500.
- Idle chat sessions expire after the session TTL; requests are rate limited per client IP and tagged with `X-Request-ID`.
- When a repair happens, clients should render the final `complete.answer`, not the streamed draft.
