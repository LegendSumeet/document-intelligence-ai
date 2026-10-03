import re
from collections import Counter

from ..models import (
    AnalysisReport,
    Citation,
    LineIndex,
    PageAnalysis,
    SearchHit,
)

ENTITY_PATTERNS = {
    "dates": re.compile(
        r"\b(?:\d{4}-\d{2}-\d{2}|\d{1,2}[/.-]\d{1,2}[/.-]\d{2,4}"
        r"|(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*\.? "
        r"\d{1,2}(?:st|nd|rd|th)?,? \d{4}"
        r"|\d{1,2} (?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]* \d{4})\b",
        re.IGNORECASE,
    ),
    "amounts": re.compile(
        r"(?:[$€£₹]\s?\d[\d,]*(?:\.\d+)?(?:\s?(?:million|billion|k|m|bn))?"
        r"|\b\d[\d,]*(?:\.\d+)?\s?(?:USD|EUR|GBP|INR)\b)",
        re.IGNORECASE,
    ),
    "percentages": re.compile(r"\b\d+(?:\.\d+)?\s?%"),
    "emails": re.compile(r"\b[\w.+-]+@[\w-]+(?:\.[\w-]+)+\b"),
    "urls": re.compile(r"https?://[^\s<>\"')]+"),
}
HEADING_PATTERN = re.compile(
    r"^(?:\d+(?:\.\d+)*[.)]?\s+)?[A-Z][A-Za-z0-9 ,&/()-]{2,80}$"
)
NUMERIC_TOKEN = re.compile(r"^[\d.,%$€£₹()-]+$")
WORD_PATTERN = re.compile(r"\w+", re.UNICODE)
WORDS_PER_MINUTE = 220
SCANNED_WORD_THRESHOLD = 10
MAX_ENTITIES_PER_KIND = 25


def _is_table_like(texts: list[str]) -> bool:
    numeric_rows = 0
    for text in texts:
        tokens = text.split()
        if len(tokens) >= 3 and sum(bool(NUMERIC_TOKEN.match(t)) for t in tokens) >= (
            len(tokens) / 2
        ):
            numeric_rows += 1
    return numeric_rows >= 3


def analyze_line_index(line_index: LineIndex) -> AnalysisReport:
    pages: list[PageAnalysis] = []
    entities: dict[str, Counter[str]] = {kind: Counter() for kind in ENTITY_PATTERNS}
    headings: list[dict] = []
    for page in line_index.pages:
        texts = [line.text for line in page.lines]
        words = sum(len(WORD_PATTERN.findall(text)) for text in texts)
        pages.append(
            PageAnalysis(
                page=page.page,
                line_count=len(texts),
                word_count=words,
                likely_scanned=words < SCANNED_WORD_THRESHOLD,
                table_like=_is_table_like(texts),
            )
        )
        for line in page.lines:
            if len(line.text.split()) <= 10 and HEADING_PATTERN.match(line.text):
                if line.text.isupper() or line.text[:1].isdigit() or len(headings) < 5:
                    headings.append(
                        {"page": page.page, "line": line.line, "text": line.text}
                    )
            for kind, pattern in ENTITY_PATTERNS.items():
                entities[kind].update(
                    match.strip() for match in pattern.findall(line.text)
                )
    total_words = sum(page.word_count for page in pages)
    scanned = [page.page for page in pages if page.likely_scanned]
    coverage = 1 - (len(scanned) / len(pages)) if pages else 0.0
    return AnalysisReport(
        doc_id=line_index.doc_id,
        name=line_index.name,
        page_count=len(pages),
        total_lines=sum(page.line_count for page in pages),
        total_words=total_words,
        reading_time_minutes=round(total_words / WORDS_PER_MINUTE, 1),
        text_coverage=round(coverage, 3),
        likely_scanned_pages=scanned,
        table_pages=[page.page for page in pages if page.table_like],
        headings=headings[:50],
        entities={
            kind: [value for value, _ in counter.most_common(MAX_ENTITIES_PER_KIND)]
            for kind, counter in entities.items()
            if counter
        },
        pages=pages,
        warnings=_warnings(pages, scanned),
    )


def _warnings(pages: list[PageAnalysis], scanned: list[int]) -> list[str]:
    warnings = []
    if not pages:
        warnings.append("The document has no pages.")
    elif len(scanned) == len(pages):
        warnings.append(
            "No extractable text found. The PDF is likely scanned and needs OCR; "
            "answers cannot be grounded in line evidence."
        )
    elif scanned:
        warnings.append(
            f"{len(scanned)} page(s) have little or no extractable text "
            "(likely scanned images); they may be missing from answers."
        )
    return warnings


def search_line_index(
    line_index: LineIndex, query: str, limit: int = 20
) -> list[SearchHit]:
    query = query.strip()
    if not query:
        raise ValueError("Search query must not be empty.")
    phrase = query.lower()
    terms = list(dict.fromkeys(WORD_PATTERN.findall(phrase)))
    if not terms:
        raise ValueError("Search query must contain letters or digits.")
    hits: list[tuple[float, SearchHit]] = []
    for page in line_index.pages:
        for line in page.lines:
            lowered = line.text.lower()
            matched = [term for term in terms if term in lowered]
            if not matched:
                continue
            score = len(matched) / len(terms)
            if phrase in lowered:
                score += 1.0
            hit = SearchHit(
                score=round(score, 3),
                citation=Citation(
                    document=line_index.name,
                    doc_id=line_index.doc_id,
                    page=page.page,
                    start_line=line.line,
                    end_line=line.line,
                    text=line.text,
                    bounding_boxes=[line.bbox],
                ),
            )
            hits.append((score, hit))
    hits.sort(
        key=lambda item: (-item[0], item[1].citation.page, item[1].citation.start_line)
    )
    return [hit for _, hit in hits[: max(1, limit)]]
