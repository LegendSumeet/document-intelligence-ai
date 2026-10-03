from typing import Any, Literal

from pydantic import BaseModel, Field


class LineEvidence(BaseModel):
    line: int
    text: str
    bbox: list[float]


class PageEvidence(BaseModel):
    page: int
    lines: list[LineEvidence]


class LineIndex(BaseModel):
    doc_id: str
    name: str
    source_path: str
    source_sha256: str
    pages: list[PageEvidence]


class Citation(BaseModel):
    document: str
    doc_id: str
    page: int
    start_line: int
    end_line: int
    text: str
    bounding_boxes: list[list[float]]
    location_verified: bool = True


class QueryResult(BaseModel):
    query_id: str
    answer: str
    documents: list[str]
    selected_pages: dict[str, list[int]]
    citations: list[Citation]
    verification_status: Literal["location_verified", "unverified"]
    usage: dict[str, Any] = Field(default_factory=dict)


class QueryEvent(BaseModel):
    type: Literal["status", "answer_delta", "validation", "complete"]
    stage: str
    message: str | None = None
    delta: str | None = None
    data: dict[str, Any] = Field(default_factory=dict)


class DocumentRecord(BaseModel):
    doc_id: str
    name: str
    source_path: str
    source_sha256: str
    status: str
    page_count: int
    collection: str = "default"
    tags: list[str] = Field(default_factory=list)


class IndexResult(BaseModel):
    document: DocumentRecord
    reused: bool


class StructuredExtraction(BaseModel):
    schema_name: str
    data: dict[str, Any]
    citations: list[Citation]


class PageAnalysis(BaseModel):
    page: int
    line_count: int
    word_count: int
    likely_scanned: bool
    table_like: bool


class AnalysisReport(BaseModel):
    doc_id: str
    name: str
    page_count: int
    total_lines: int
    total_words: int
    reading_time_minutes: float
    text_coverage: float
    likely_scanned_pages: list[int]
    table_pages: list[int]
    headings: list[dict[str, Any]]
    entities: dict[str, list[str]]
    pages: list[PageAnalysis]
    warnings: list[str] = Field(default_factory=list)


class SearchHit(BaseModel):
    score: float
    citation: Citation
