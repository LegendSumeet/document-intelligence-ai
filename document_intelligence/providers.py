from openai import AzureOpenAI
from pageindex import PageIndexClient

from .config import Settings


def create_pageindex_client(settings: Settings) -> PageIndexClient:
    backend = {
        "api_key": settings.azure_api_key,
        "base_url": settings.azure_endpoint,
        "api_version": settings.azure_api_version,
    }
    return PageIndexClient(
        index={
            "model": f"azure/{settings.index_model}",
            "backend": backend,
            "storage_path": str(settings.storage_path),
        },
        chat={"model": f"azure/{settings.chat_model}", "backend": backend},
    )


def create_azure_client(settings: Settings) -> AzureOpenAI:
    return AzureOpenAI(
        api_key=settings.azure_api_key,
        azure_endpoint=settings.azure_endpoint,
        api_version=settings.azure_api_version,
    )
