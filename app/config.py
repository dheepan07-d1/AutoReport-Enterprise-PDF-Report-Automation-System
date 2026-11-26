"""Centralized configuration management and input validation for AutoReport."""

from __future__ import annotations

import math
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlparse

from dotenv import load_dotenv

from app.exceptions import ConfigurationError, ValidationError
from app.logger import VALID_LOG_LEVELS

VALID_SCHEDULE_INTERVALS = ("daily", "hourly", "minutes")
_TIME_PATTERN = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)$")


def _default_base_dir() -> Path:
    """Resolve the default project root directory."""
    return Path(__file__).resolve().parent.parent


def validate_coordinates(latitude: float, longitude: float) -> tuple[float, float]:
    """Validate geographic latitude and longitude values.

    Args:
        latitude: Latitude in decimal degrees [-90, 90].
        longitude: Longitude in decimal degrees [-180, 180].

    Returns:
        Validated (latitude, longitude) tuple as floats.

    Raises:
        ValidationError: If either coordinate is out of bounds or non-finite.
    """
    try:
        lat = float(latitude)
        lon = float(longitude)
    except (TypeError, ValueError) as exc:
        raise ValidationError(
            f"Coordinates must be numeric values (got latitude={latitude!r}, longitude={longitude!r})."
        ) from exc

    if not math.isfinite(lat) or not math.isfinite(lon):
        raise ValidationError("Latitude and longitude must be finite numbers.")
    if not (-90.0 <= lat <= 90.0):
        raise ValidationError(f"Latitude must be between -90 and 90 (got {lat}).")
    if not (-180.0 <= lon <= 180.0):
        raise ValidationError(f"Longitude must be between -180 and 180 (got {lon}).")
    return lat, lon


def validate_forecast_days(days: int) -> int:
    """Validate forecast day count (Open-Meteo supports 1 to 16 days)."""
    try:
        parsed = int(days)
    except (TypeError, ValueError) as exc:
        raise ValidationError(f"Forecast days must be an integer (got {days!r}).") from exc

    if not (1 <= parsed <= 16):
        raise ValidationError(f"Forecast days must be between 1 and 16 (got {parsed}).")
    return parsed


def validate_schedule_time(time_str: str) -> tuple[int, int]:
    """Validate a 24-hour HH:MM schedule execution time."""
    if not isinstance(time_str, str):
        raise ValidationError(f"Schedule time must be a string in HH:MM format (got {time_str!r}).")
    match = _TIME_PATTERN.match(time_str.strip())
    if not match:
        raise ValidationError(
            f"Invalid schedule time '{time_str}'. Expected 24-hour HH:MM format (00:00-23:59)."
        )
    return int(match.group(1)), int(match.group(2))


def validate_schedule_interval(interval: str) -> str:
    """Validate scheduling interval mode."""
    normalized = interval.strip().lower() if isinstance(interval, str) else ""
    if normalized not in VALID_SCHEDULE_INTERVALS:
        raise ValidationError(
            f"Invalid schedule interval '{interval}'. "
            f"Choose from: {', '.join(VALID_SCHEDULE_INTERVALS)}."
        )
    return normalized


def _parse_float_env(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    try:
        return float(raw.strip())
    except ValueError as exc:
        raise ConfigurationError(f"Environment variable {name} must be numeric (got {raw!r}).") from exc


def _parse_int_env(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    try:
        return int(raw.strip())
    except ValueError as exc:
        raise ConfigurationError(f"Environment variable {name} must be an integer (got {raw!r}).") from exc


@dataclass
class AppConfig:
    """Centralized configuration container for AutoReport."""

    app_name: str = "AutoReport"
    version: str = "1.0.0"
    api_base_url: str = "https://api.open-meteo.com/v1/forecast"
    request_timeout: float = 15.0
    default_latitude: float = 11.0168
    default_longitude: float = 76.9558
    default_location_name: str = "Coimbatore, IN"
    forecast_days: int = 7
    timezone: str = "auto"
    base_dir: Path = field(default_factory=_default_base_dir)
    log_level: str = "INFO"
    schedule_interval: str = "daily"
    schedule_time: str = "08:00"
    schedule_interval_minutes: int = 60

    @property
    def data_dir(self) -> Path:
        """Directory for intermediate/processed data snapshots."""
        return self.base_dir / "data"

    @property
    def reports_dir(self) -> Path:
        """Directory for generated PDF reports."""
        return self.base_dir / "reports"

    @property
    def logs_dir(self) -> Path:
        """Directory for application log files."""
        return self.base_dir / "logs"

    @property
    def charts_dir(self) -> Path:
        """Directory for generated Matplotlib charts."""
        return self.base_dir / "charts"

    @property
    def log_file(self) -> Path:
        """Primary application log file path."""
        return self.logs_dir / "app.log"

    @classmethod
    def from_env(cls, env_path: Path | None = None, base_dir: Path | None = None) -> "AppConfig":
        """Load configuration from environment variables and optional .env file."""
        if env_path is not None:
            load_dotenv(dotenv_path=env_path, override=False)
        else:
            load_dotenv(override=False)

        resolved_base = (
            base_dir
            if base_dir is not None
            else Path(os.getenv("AUTOREPORT_BASE_DIR", str(_default_base_dir()))).resolve()
        )

        return cls(
            api_base_url=os.getenv(
                "AUTOREPORT_API_BASE_URL", "https://api.open-meteo.com/v1/forecast"
            ).strip(),
            request_timeout=_parse_float_env("AUTOREPORT_REQUEST_TIMEOUT", 15.0),
            default_latitude=_parse_float_env("AUTOREPORT_DEFAULT_LATITUDE", 11.0168),
            default_longitude=_parse_float_env("AUTOREPORT_DEFAULT_LONGITUDE", 76.9558),
            default_location_name=os.getenv(
                "AUTOREPORT_DEFAULT_LOCATION_NAME", "Coimbatore, IN"
            ).strip()
            or "Custom Location",
            forecast_days=_parse_int_env("AUTOREPORT_FORECAST_DAYS", 7),
            timezone=os.getenv("AUTOREPORT_TIMEZONE", "auto").strip() or "auto",
            base_dir=resolved_base,
            log_level=os.getenv("AUTOREPORT_LOG_LEVEL", "INFO").strip().upper(),
            schedule_interval=os.getenv("AUTOREPORT_SCHEDULE_INTERVAL", "daily").strip().lower(),
            schedule_time=os.getenv("AUTOREPORT_SCHEDULE_TIME", "08:00").strip(),
            schedule_interval_minutes=_parse_int_env("AUTOREPORT_SCHEDULE_INTERVAL_MINUTES", 60),
        )

    def ensure_directories(self) -> None:
        """Ensure required workspace output directories exist and are writable."""
        for directory in (self.data_dir, self.reports_dir, self.logs_dir, self.charts_dir):
            try:
                directory.mkdir(parents=True, exist_ok=True)
            except OSError as exc:
                raise ConfigurationError(
                    f"Cannot create required directory '{directory}': {exc}"
                ) from exc
            if not os.access(directory, os.W_OK):
                raise ConfigurationError(f"Directory '{directory}' is not writable.")

    def validate(self) -> list[str]:
        """Validate all configuration parameters and workspace directories.

        Returns:
            List of human-readable validation check descriptions.

        Raises:
            ConfigurationError: If configuration values or directories are invalid.
            ValidationError: If coordinates, forecast days, or schedule parameters are invalid.
        """
        parsed_url = urlparse(self.api_base_url)
        if parsed_url.scheme not in ("http", "https") or not parsed_url.netloc:
            raise ConfigurationError(
                f"Invalid API base URL '{self.api_base_url}'. Must be a valid HTTP/HTTPS URL."
            )

        if not math.isfinite(self.request_timeout) or self.request_timeout <= 0:
            raise ConfigurationError(
                f"Request timeout must be a positive number (got {self.request_timeout})."
            )

        validate_coordinates(self.default_latitude, self.default_longitude)
        validate_forecast_days(self.forecast_days)

        if self.log_level.upper() not in VALID_LOG_LEVELS:
            raise ConfigurationError(
                f"Invalid log level '{self.log_level}'. Choose from {sorted(VALID_LOG_LEVELS)}."
            )

        validate_schedule_interval(self.schedule_interval)
        validate_schedule_time(self.schedule_time)
        if self.schedule_interval_minutes < 1:
            raise ConfigurationError(
                f"Schedule interval minutes must be >= 1 (got {self.schedule_interval_minutes})."
            )

        self.ensure_directories()

        return [
            f"API Endpoint: {self.api_base_url} (timeout={self.request_timeout}s)",
            f"Default Location: {self.default_location_name} ({self.default_latitude}, {self.default_longitude})",
            f"Forecast Window: {self.forecast_days} days (timezone={self.timezone})",
            f"Logging: level={self.log_level}, file={self.log_file}",
            f"Schedule: interval={self.schedule_interval}, time={self.schedule_time}, minutes={self.schedule_interval_minutes}",
            f"Directories verified: data, reports, logs, charts under {self.base_dir}",
        ]
