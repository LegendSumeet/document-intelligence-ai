# Improvement Plan: Stability, Document Analysis, Search

## Findings from the current code

| # | Area | Problem | Impact |
|---|------|---------|--------|
| 1 | Answers | One bad citation raises `ValueError`, so the user gets a 422 and no answer | Flaky answers |
| 2 | Answers | No cap on evidence size sent to the model | Context overflow on big pages |
| 3 | Azure client | No timeout or retry configuration | Hung requests |
| 4 | API errors | `OpenAIError`, invalid page specs and missing line indexes surface as HTTP 500 | Poor client errors |
| 5 | API | `/queries` and `/extractions` skip document readiness checks | Confusing failures |
| 6 | Sessions | In-memory sessions never expire | Memory growth |
| 7 | Ops | No logging, request IDs, rate limiting or readiness probe | Hard to run safely |
| 8 | Extraction | JSON parsing breaks on code fences or stray braces in prose | Failed extractions |
| 9 | Product | No document analysis, no deterministic search, no insight presets | Missing core features |

## Work items

1. **Reliability**
   - Azure `timeout` / `max_retries` settings.
   - One-shot citation repair: if validation fails, ask the model to fix its citations, then validate again.
   - Evidence budget (`max_evidence_chars`) that drops trailing pages and reports what was used.
   - Robust JSON extraction (fenced or embedded JSON).
2. **API hardening**
   - Central error mapping: OpenAI/PageIndex errors become 502/503, bad input becomes 422, missing index becomes 404.
   - Document readiness validation on queries and extractions.
   - Session TTL eviction.
   - Per-client rate limiting.
   - Request-ID and logging middleware, `/health/ready`.
3. **Document analysis (deterministic, no model calls)**
   - Per-page stats, scanned/empty-page detection, heading and table-likeness heuristics, key entities (dates, amounts, emails, URLs, percentages), reading-time estimate, overall quality score.
   - `GET /documents/{id}/analysis`, CLI `analyze`.
4. **Search (deterministic)**
   - Ranked keyword/phrase search over numbered lines, returning citation-shaped hits with bounding boxes.
   - `GET /documents/{id}/search?q=`, CLI `search`.
5. **AI insights presets**
   - `summary`, `key_facts`, `risks`, `obligations`, `action_items`, each as a cited extraction.
   - `POST /documents/{id}/insights/{kind}`, CLI `insights`.
6. **Quality**
   - Tests for every item (no network), docs updated (`FEATURES.md`, `README.md`).

## Out of scope

Persistent storage, user accounts, OCR engines and non-PDF formats (these stay deferred per `FEATURES.md`).
