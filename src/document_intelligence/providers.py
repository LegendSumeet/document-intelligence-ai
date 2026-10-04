from openai import OpenAI
from pageindex import PageIndexClient

from .config import Settings

GEMINI_OPENAI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"


def create_pageindex_client(settings: Settings) -> PageIndexClient:
    backend = {"api_key": settings.gemini_api_key}
    return PageIndexClient(
        index={
            "model": f"gemini/{settings.index_model}",
            "backend": backend,
            "storage_path": str(settings.storage_path),
        },
        chat={"model": f"gemini/{settings.chat_model}", "backend": backend},
    )


def create_llm_client(settings: Settings) -> OpenAI:
    return OpenAI(
        api_key=settings.gemini_api_key,
        base_url=GEMINI_OPENAI_BASE_URL,
        timeout=settings.llm_timeout_seconds,
        max_retries=settings.llm_max_retries,
    )
