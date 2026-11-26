"""REST API client for retrieving weather forecast data from Open-Meteo."""

from __future__ import annotations

import logging
from datetime import datetime, timezone as dt_timezone
from typing import Any

import requests

from app.config import validate_coordinates, validate_forecast_days
from app.exceptions import (
    APIConnectionError,
    APIRateLimitError,
    APIResponseError,
    APITimeoutError,
)


class WeatherAPIClient:
    """Client for communicating with the Open-Meteo Forecast REST API."""

    DAILY_VARIABLES = (
        "temperature_2m_max,"
        "temperature_2m_min,"
        "temperature_2m_mean,"
        "precipitation_sum,"
        "windspeed_10m_max,"
        "weathercode"
    )

    def __init__(
        self,
        base_url: str = "https://api.open-meteo.com/v1/forecast",
        timeout: float = 15.0,
        logger: logging.Logger | None = None,
        session: requests.Session | None = None,
    ) -> None:
        self.base_url = base_url
        self.timeout = timeout
        self.logger = logger or logging.getLogger("autoreport.api")
        self.session = session or requests.Session()

    def fetch_weather_forecast(
        self,
        latitude: float,
        longitude: float,
        forecast_days: int = 7,
        timezone: str = "auto",
        location_name: str | None = None,
    ) -> dict[str, Any]:
        """Fetch and validate daily weather forecast data from Open-Meteo.

        Args:
            latitude: Target latitude in decimal degrees.
            longitude: Target longitude in decimal degrees.
            forecast_days: Number of forecast days (1-16).
            timezone: Timezone identifier or ``"auto"``.
            location_name: Optional human-readable location label.

        Returns:
            Validated JSON payload augmented with ``metadata``.

        Raises:
            ValidationError: If coordinates or forecast_days are invalid.
            APITimeoutError: If the HTTP request times out.
            APIConnectionError: If a network connection error occurs.
            APIRateLimitError: If the API responds with HTTP 429.
            APIResponseError: If HTTP status is non-200 or JSON payload is invalid.
        """
        lat, lon = validate_coordinates(latitude, longitude)
        days = validate_forecast_days(forecast_days)

        params = {
            "latitude": lat,
            "longitude": lon,
            "daily": self.DAILY_VARIABLES,
            "current_weather": "true",
            "timezone": timezone,
            "forecast_days": days,
        }

        self.logger.info(
            "Requesting weather forecast from API (lat=%.4f, lon=%.4f, days=%d, timeout=%.1fs)",
            lat,
            lon,
            days,
            self.timeout,
        )

        try:
            response = self.session.get(self.base_url, params=params, timeout=self.timeout)
        except requests.exceptions.Timeout as exc:
            self.logger.error("API request timed out after %.1fs: %s", self.timeout, exc)
            raise APITimeoutError(
                f"Weather API request timed out after {self.timeout} seconds."
            ) from exc
        except requests.exceptions.ConnectionError as exc:
            self.logger.error("Failed to connect to weather API: %s", exc)
            raise APIConnectionError(
                "Unable to connect to the Open-Meteo weather API. Check your internet connection."
            ) from exc
        except requests.exceptions.RequestException as exc:
            self.logger.error("Unexpected transport error during API request: %s", exc)
            raise APIConnectionError(f"Weather API request failed: {exc}") from exc

        if response.status_code == 429:
            self.logger.warning("Weather API rate limit encountered (HTTP 429).")
            raise APIRateLimitError(
                "Weather API rate limit exceeded (HTTP 429). Please retry later."
            )

        if response.status_code >= 400:
            self.logger.error("Weather API returned HTTP error status %d.", response.status_code)
            raise APIResponseError(
                f"Weather API returned HTTP {response.status_code}: {response.text[:200]}"
            )

        try:
            payload = response.json()
        except ValueError as exc:
            self.logger.error("Weather API returned invalid JSON: %s", exc)
            raise APIResponseError("Weather API returned malformed JSON data.") from exc

        self._validate_payload(payload)

        resolved_name = location_name or f"Lat {lat:.4f}, Lon {lon:.4f}"
        now_iso = datetime.now(dt_timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        payload["metadata"] = {
            "location_name": resolved_name,
            "source": "Open-Meteo Forecast REST API (api.open-meteo.com)",
            "is_demo": False,
            "demo_notice": "",
            "fetched_at": now_iso,
            "api_url": self.base_url,
        }

        self.logger.info(
            "Successfully retrieved and validated %d forecast days from Open-Meteo API.",
            len(payload["daily"]["time"]),
        )
        return payload

    @staticmethod
    def _validate_payload(payload: Any) -> None:
        """Validate that the API JSON response has the required daily structure."""
        if not isinstance(payload, dict):
            raise APIResponseError("Weather API response root must be a JSON object.")

        if payload.get("error") is True:
            reason = payload.get("reason", "Unknown API error")
            raise APIResponseError(f"Weather API reported an error: {reason}")

        daily = payload.get("daily")
        if not isinstance(daily, dict):
            raise APIResponseError("Weather API response is missing the 'daily' data section.")

        required_fields = ("time", "temperature_2m_max", "temperature_2m_min")
        for field_name in required_fields:
            values = daily.get(field_name)
            if not isinstance(values, list) or len(values) == 0:
                raise APIResponseError(
                    f"Weather API response 'daily.{field_name}' must be a non-empty list."
                )

        expected_length = len(daily["time"])
        for key, values in daily.items():
            if not isinstance(values, list):
                raise APIResponseError(
                    f"Weather API response 'daily.{key}' must be a list."
                )
            if len(values) != expected_length:
                raise APIResponseError(
                    f"Weather API response length mismatch in 'daily.{key}': "
                    f"expected {expected_length}, got {len(values)}."
                )
