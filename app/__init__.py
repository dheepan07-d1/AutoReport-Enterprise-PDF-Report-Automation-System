"""AutoReport – Enterprise PDF Report Automation System."""

from app.config import AppConfig
from app.exceptions import (
    APIConnectionError,
    APIRateLimitError,
    APIResponseError,
    APITimeoutError,
    AutoReportError,
    ConfigurationError,
    DataProcessingError,
    PDFGenerationError,
    SchedulerError,
    ValidationError,
)

__app_name__ = "AutoReport"
__version__ = "1.0.0"

__all__ = [
    "__app_name__",
    "__version__",
    "AppConfig",
    "AutoReportError",
    "ConfigurationError",
    "ValidationError",
    "APIConnectionError",
    "APITimeoutError",
    "APIRateLimitError",
    "APIResponseError",
    "DataProcessingError",
    "PDFGenerationError",
    "SchedulerError",
]
