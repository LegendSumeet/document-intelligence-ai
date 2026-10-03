from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


@dataclass(frozen=True)
class Settings:
    storage_path: Path
    upload_path: Path
    azure_api_key: str
    azure_endpoint: str
    azure_api_version: str
    index_model: str
    chat_model: str
    client_api_key: str
    max_upload_bytes: int = 100 * 1024 * 1024
    azure_timeout_seconds: float = 120.0
    azure_max_retries: int = 3
    max_evidence_chars: int = 120_000
    session_ttl_seconds: int = 6 * 3600
    rate_limit_per_minute: int = 120
    cors_origins: tuple[str, ...] = (
        "http://localhost",
        "http://localhost:3000",
        "http://localhost:8080",
    )

    @classmethod
    def from_env(cls, storage_path: str | None = None) -> Settings:
        load_dotenv()
        root = Path(storage_path or os.getenv("PAGEINDEX_STORAGE_PATH", ".pageindex"))

        def required(name: str) -> str:
            value = os.getenv(name)
            if not value:
                raise ValueError(f"Missing required environment variable: {name}")
            return value

        def number(name: str, default, cast):
            raw = os.getenv(name)
            if raw is None or not raw.strip():
                return default
            try:
                value = cast(raw)
            except ValueError as error:
                raise ValueError(f"{name} must be a number, got {raw!r}") from error
            if value < 0:
                raise ValueError(f"{name} must not be negative")
            return value

        return cls(
            storage_path=root,
            upload_path=root / "uploads",
            azure_api_key=required("AZURE_OPENAI_API_KEY"),
            azure_endpoint=required("AZURE_OPENAI_ENDPOINT"),
            azure_api_version=required("AZURE_OPENAI_API_VERSION"),
            index_model=required("AZURE_OPENAI_PRIMARY_MODEL"),
            chat_model=required("AZURE_OPENAI_CHAT_MODEL"),
            client_api_key=required("DOCUMENT_INTELLIGENCE_API_KEY"),
            azure_timeout_seconds=number("AZURE_OPENAI_TIMEOUT_SECONDS", 120.0, float),
            azure_max_retries=number("AZURE_OPENAI_MAX_RETRIES", 3, int),
            max_evidence_chars=number(
                "DOCUMENT_INTELLIGENCE_MAX_EVIDENCE_CHARS", 120_000, int
            ),
            session_ttl_seconds=number(
                "DOCUMENT_INTELLIGENCE_SESSION_TTL_SECONDS", 6 * 3600, int
            ),
            rate_limit_per_minute=number(
                "DOCUMENT_INTELLIGENCE_RATE_LIMIT_PER_MINUTE", 120, int
            ),
            cors_origins=tuple(
                origin.strip()
                for origin in os.getenv(
                    "DOCUMENT_INTELLIGENCE_CORS_ORIGINS",
                    "http://localhost,http://localhost:3000,http://localhost:8080",
                ).split(",")
                if origin.strip()
            ),
        )

    def ensure_directories(self) -> None:
        self.storage_path.mkdir(parents=True, exist_ok=True)
        self.upload_path.mkdir(parents=True, exist_ok=True)
