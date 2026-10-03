import re
from collections.abc import Sequence
from typing import Any

from ..models import Citation, LineIndex

LINE_CITATION_PATTERN = re.compile(
    r'<cite doc="(?P<doc>[^"]+)" page="(?P<page>\d+)" '
    r'lines="(?P<start>\d+)(?:-(?P<end>\d+))?"\s*/>'
)
PAGE_CITATION_PATTERN = re.compile(
    r'<cite\s+[^>]*doc="(?P<doc>[^"]+)"[^>]*page="(?P<page>\d+)"[^>]*/>'
)


def parse_page_spec(page_spec: str) -> list[int]:
    pages = set()
    for part in page_spec.split(","):
        bounds = part.strip().split("-", maxsplit=1)
        try:
            start = int(bounds[0])
            end = int(bounds[-1])
        except ValueError as error:
            raise ValueError(f"Invalid page selection: {page_spec}") from error
        if start < 1 or end < start:
            raise ValueError(f"Invalid page selection: {page_spec}")
        pages.update(range(start, end + 1))
    return sorted(pages)


def evidence_for_pages(line_index: LineIndex, page_numbers: list[int]) -> str:
    requested = set(page_numbers)
    sections = []
    available = {page.page for page in line_index.pages}
    missing = requested - available
    if missing:
        raise ValueError(
            f"Selected pages are missing from the local line index: {missing}"
        )
    for page in line_index.pages:
        if page.page in requested:
            lines = "\n".join(f"L{line.line}: {line.text}" for line in page.lines)
            sections.append(f"--- {line_index.name} page {page.page} ---\n{lines}")
    return "\n\n".join(sections)


def validate_line_citations(
    answer: str,
    line_indexes: Sequence[LineIndex | dict[str, Any]],
    selected_pages: dict[str, list[int]],
) -> list[dict[str, Any]]:
    indexes = [
        item if isinstance(item, LineIndex) else LineIndex.model_validate(item)
        for item in line_indexes
    ]
    matches = list(LINE_CITATION_PATTERN.finditer(answer))
    if not matches:
        raise ValueError("The grounded answer contained no valid line citations.")
    indexes_by_name = {item.name: item for item in indexes}
    resolved: list[dict[str, Any]] = []
    for match in matches:
        name = match.group("doc")
        page_number = int(match.group("page"))
        start = int(match.group("start"))
        end = int(match.group("end") or start)
        line_index = indexes_by_name.get(name)
        if line_index is None:
            raise ValueError(f"Citation names an unknown document: {name}")
        if page_number not in selected_pages.get(name, []):
            raise ValueError(
                f"Citation points outside the supplied evidence: {match.group(0)}"
            )
        page = next(
            (item for item in line_index.pages if item.page == page_number), None
        )
        if page is None or not (1 <= start <= end <= len(page.lines)):
            raise ValueError(f"Citation points outside the source: {match.group(0)}")
        lines = page.lines[start - 1 : end]
        resolved.append(
            Citation(
                document=name,
                doc_id=line_index.doc_id,
                page=page_number,
                start_line=start,
                end_line=end,
                text="\n".join(line.text for line in lines),
                bounding_boxes=[line.bbox for line in lines],
            ).model_dump()
        )
    return resolved
