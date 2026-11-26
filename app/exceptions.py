"""Custom exception hierarchy for AutoReport."""


class AutoReportError(Exception):
    """Base exception for all AutoReport errors."""


class ConfigurationError(AutoReportError):
    """Raised when application configuration is invalid or directories are inaccessible."""


class ValidationError(AutoReportError):
    """Raised when user inputs or external data fail validation."""


class APIConnectionError(AutoReportError):
    """Raised when connecting to the external REST API fails."""


class APITimeoutError(AutoReportError):
    """Raised when an external API request exceeds the configured timeout."""


class APIRateLimitError(AutoReportError):
    """Raised when the external API returns HTTP 429 rate limiting."""


class APIResponseError(AutoReportError):
    """Raised when the external API returns an HTTP error or malformed payload."""


class DataProcessingError(AutoReportError):
    """Raised when cleaning, transforming, or analyzing weather data fails."""


class PDFGenerationError(AutoReportError):
    """Raised when chart rendering or PDF generation fails."""


class SchedulerError(AutoReportError):
    """Raised when initializing, configuring, or running the scheduler fails."""
