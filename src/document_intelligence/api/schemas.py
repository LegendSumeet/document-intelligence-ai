import json
from typing import Any

from pydantic import BaseModel, Field


class QueryRequest(BaseModel):
    document_ids: list[str] = Field(min_length=1)
    question: str = Field(min_length=1)
    reasoning_effort: str | None = None


class ExtractionRequest(BaseModel):
    document_ids: list[str] = Field(min_length=1)
    instruction: str = Field(min_length=1)
    schema_name: str = "custom"


class SessionRequest(BaseModel):
    document_ids: list[str] = Field(min_length=1)


class MessageRequest(BaseModel):
    message: str = Field(min_length=1)
    reasoning_effort: str | None = None


def sse_event(event: str, data: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"
