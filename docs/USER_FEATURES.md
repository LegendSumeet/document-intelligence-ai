# Document Intelligence AI

Turn long PDF documents into clear, source-backed answers.

Document Intelligence AI helps you upload, explore, compare, and extract
information from PDFs without manually reading every page. Answers include
citations that take you back to the exact source text, so important information
can be checked quickly.

## What You Can Do

### Ask Questions About Your Documents

Ask questions in everyday language and receive answers based on the content of
your selected PDFs.

Example questions:

- "What are the main risks in this report?"
- "When does this agreement expire?"
- "Summarize the candidate's work experience."
- "What payment terms are mentioned in this document?"

The system searches the relevant sections before preparing an answer, which
means you do not need to know the page number or exact wording in advance.

### Check Every Answer Against Its Source

Answers include citations to the original document, page, and line range. Each
citation can be resolved to:

- The source PDF
- The exact page
- The quoted source text
- The location of the text on the page

This makes it easier to review important details instead of accepting an AI
answer without evidence.

### Chat With Your Documents

Continue the conversation with follow-up questions. The chat remembers recent
messages during the current session, allowing questions such as:

1. "Summarize the key obligations."
2. "Which of those obligations has the earliest deadline?"
3. "Show me the evidence for that deadline."

You can also see live progress while the system searches documents, selects
evidence, generates an answer, and validates its citations.

### Work With Multiple Documents

Select more than one PDF to compare or combine information across documents.

Example requests:

- "Compare the experience of these candidates."
- "How did the reported risks change between these two reports?"
- "Which terms are different across these agreements?"
- "Create one summary using all selected documents."

Citations remain connected to the correct source document.

### Extract Structured Information

Turn document content into structured JSON that can be used by another
application or workflow.

Example requests:

- Extract names, dates, skills, and employment history
- Extract parties, obligations, deadlines, and termination terms
- Extract totals, taxes, payment terms, and supplier details
- Extract key metrics, reporting periods, and risks

The result includes supporting citations so extracted information can be
reviewed against the PDF.

### Explore Document Contents

After a PDF is processed, you can:

- View its title and metadata
- Check whether it is ready for questions
- Browse its section hierarchy
- Inspect exact numbered text from individual pages
- Open the original PDF
- Retrieve text locations for highlighting in a PDF viewer

## Typical User Journey

1. Upload a text-based PDF.
2. Wait for the document to finish processing.
3. Select one or more documents.
4. Ask a question or request structured information.
5. Review the answer and open its citations.
6. Ask follow-up questions or compare another document.

## Trust And Transparency

### Verified Citation Locations

Before an answer is returned as validated, the system checks that every
citation points to:

- A document included in the question
- A page that was supplied to the AI
- A line range that exists on that page

The exact source text and its PDF coordinates are returned with structured
results.

### Focused Evidence

The AI answers from the pages selected as relevant to the question. This keeps
the response grounded in document evidence and reduces unrelated information.

### Clear Validation State

During streaming chat, text is shown as a draft while it is generated. It is
marked as validated only after all citation locations pass validation.

### Local Document Indexes

Document indexes and extracted line evidence are stored locally by the current
application. Azure OpenAI is used to perform AI generation, so selected evidence
is sent to the configured Azure OpenAI service.

## Supported Documents

The current version supports PDFs that contain selectable text, including many:

- Reports
- Contracts and agreements
- Resumes and CVs
- Policies and manuals
- Research documents
- Financial documents

The quality of results depends on the quality and structure of the source PDF.

## Current Limitations

- Scanned or image-only PDFs are not currently supported because OCR is not yet
  available.
- Images, charts, figures, and diagrams are not interpreted.
- PDF is the only supported upload format.
- Chat sessions are temporary and disappear when the application restarts.
- Document processing currently happens during upload, so large documents can
  take time before the upload request completes.
- Citation validation confirms that a cited location exists. It does not prove
  that every statement is logically supported by the citation. Important or
  high-stakes answers should still be reviewed by a person.

## Coming Next

Planned improvements include:

- Support for scanned PDFs through OCR
- Understanding of tables, images, charts, and diagrams
- Word document, HTML, and image uploads
- Ready-made extraction templates for resumes, contracts, invoices, and reports
- Stronger claim-by-claim evidence verification
- Confidence and evidence coverage indicators
- Clickable PDF citations with highlighted source text
- Side-by-side document comparison
- Export to CSV, Markdown, JSON, and annotated PDF
- Persistent conversation history
- Faster background document processing with progress updates

## Best Suited For

Document Intelligence AI is useful when people need to understand long or
numerous documents while keeping the original evidence visible. It can support
document review, research, candidate screening, contract analysis, policy
navigation, report comparison, and structured data collection.

It is designed to assist review and decision-making, not to replace legal,
financial, medical, compliance, or other professional judgment.
