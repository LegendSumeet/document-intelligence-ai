# Document Intelligence with PageIndex Flash

This project uses `PageIndexClient` in local mode with Azure OpenAI. PageIndex
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
AZURE_OPENAI_API_KEY=...
AZURE_OPENAI_ENDPOINT=https://YOUR-RESOURCE.openai.azure.com
AZURE_OPENAI_API_VERSION=...
AZURE_OPENAI_PRIMARY_MODEL=YOUR-LOW-COST-INDEX-DEPLOYMENT
AZURE_OPENAI_CHAT_MODEL=YOUR-STRONG-CHAT-DEPLOYMENT
```

The model values are Azure deployment names. A smaller model is usually enough
for indexing; retrieval quality depends more heavily on the chat model.

## Usage

Index a PDF once:

```bash
uv run python main.py index ./test.pdf
```

Running the same command again reuses the existing document ID. Use `--force`
only when the PDF changed and you intentionally want a new index:

```bash
uv run python main.py index ./test.pdf --force
```

Save the returned document ID, then reuse the persisted index for questions:

```bash
uv run python main.py ask DOC_ID "Tell me about Sumeet Vishwakarma"
```

By default, `ask` first uses PageIndex to select relevant pages, then asks Azure
OpenAI to answer only from locally numbered evidence. It validates that every
result contains citations whose document, page, and line ranges exist:

```text
Sumeet is a founding engineer. <cite doc="test_1.pdf" page="1" lines="16-18"/>
```

Useful options:

```bash
uv run python main.py list
uv run python main.py info DOC_ID
uv run python main.py structure DOC_ID
uv run python main.py pages DOC_ID "1-2"
uv run python main.py ask DOC_ID "Summarize the document" --reasoning-effort high
uv run python main.py ask DOC_ID "Summarize the document" --show-process
uv run python main.py ask DOC_ID "Summarize the document" --json
uv run python main.py ask DOC_ID "Summarize the document" --page-citations
uv run python main.py extract DOC_ID "Extract education and work history"
uv run python main.py chat --show-process
```

The interactive `chat` command lists indexed documents first. Select one or
multiple documents by number, then ask questions against that fixed scope. Use
`docs` to view the current selection, `use` to change it, and `exit` to finish.
Each question displays document scoping, PageIndex tree retrieval, selected
evidence pages, grounded generation, and citation validation. Answer tokens are
streamed as a draft and marked verified only after all citations pass. Recent
turns are kept in memory for follow-up questions. Use `--quiet-process` to hide
stage messages while retaining answer streaming.

Compare or synthesize across documents by repeating `--with-doc`:

```bash
uv run python main.py ask DOC_ID "Compare the candidates' experience" \
	--with-doc ANOTHER_DOC_ID
```

Multi-document answers retain verified line citations. `--json` resolves each
citation to its document ID, exact text, and PDF bounding boxes, making the
result suitable for an API response or a source-highlighting interface.

## API

Start the local API:

```bash
uv run fastapi dev document_intelligence/api.py
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
