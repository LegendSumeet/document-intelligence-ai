"""Local-first document intelligence built on PageIndex."""

from .config import Settings
from .services import DocumentService, QueryService

__all__ = ["DocumentService", "QueryService", "Settings"]
