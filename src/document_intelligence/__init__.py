"""Local-first document intelligence built on PageIndex."""

from .config import Settings
from .services import DocumentService, QueryService

__version__ = "0.4.0"
__all__ = ["DocumentService", "QueryService", "Settings", "__version__"]
