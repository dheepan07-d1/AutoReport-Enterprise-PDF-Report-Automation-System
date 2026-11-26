"""Offline demonstration weather data provider (kept separate from live API)."""

from __future__ import annotations

import math
from datetime import date, datetime, timedelta, timezone as dt_timezone
from typing import Any

from app.config import validate_coordinates, validate_forecast_days

DEMO_NOTICE = (
    "DEMONSTRATION DATA ONLY — Generated from offline simulated sample data. "
    "Values do not represent live meteorological observations."
)


class SampleWeatherProvider:
    """Provides deterministic offline sample weather forecasts for demonstration mode."""

    SOURCE_LABEL = "Offline Demonstration Sample Dataset (Simulated)"

    def get_weather_forecast(
        self,
        latitude: float = 11.0168,
        longitude: float = 76.9558,
        forecast_days: int = 7,
        location_name: str | None = None,
        timezone: str = "auto",
        start_date: date | None = None,
    ) -> dict[str, Any]:
        """Build a deterministic offline sample dataset matching the Open-Meteo schema.

        Args:
            latitude: Geographic latitude for coordinate metadata and temperature baseline.
            longitude: Geographic longitude for coordinate metadata.
            forecast_days: Number of daily records to synthesize (1-16).
            location_name: Optional friendly display name for the location.
            timezone: Timezone label stored in payload metadata.
            start_date: Optional starting calendar date (defaults to today's date).

        Returns:
            Normalized weather payload explicitly marked as demonstration data.
        """
        lat, lon = validate_coordinates(latitude, longitude)
        days_count = validate_forecast_days(forecast_days)
        anchor_date = start_date or datetime.now().date()

        # Estimate a plausible baseline temperature from latitude so sample data scales naturally.
        tropical_factor = max(0.0, 1.0 - abs(lat) / 65.0)
        base_mean = 12.0 + 17.5 * tropical_factor

        dates: list[str] = []
        temp_max: list[float] = []
        temp_min: list[float] = []
        temp_mean: list[float] = []
        precipitation: list[float] = []
        windspeed: list[float] = []
        weather_codes: list[int] = []

        precip_pattern = [0.0, 1.4, 6.8, 12.5, 2.1, 0.0, 0.4, 3.2]
        code_pattern = [0, 2, 61, 63, 3, 1, 2, 80]

        for idx in range(days_count):
            day = anchor_date + timedelta(days=idx)
            wave = math.sin((idx + abs(lon) * 0.05) * 0.85) * 2.1
            daily_mean = round(base_mean + wave, 1)
            daily_min = round(daily_mean - (4.2 + (idx % 3) * 0.6), 1)
            daily_max = round(daily_mean + (4.8 + ((idx + 1) % 3) * 0.5), 1)
            precip = round(precip_pattern[idx % len(precip_pattern)], 1)
            wind = round(10.5 + (idx % 4) * 2.8 + abs(math.cos(idx)) * 1.7, 1)
            wcode = code_pattern[idx % len(code_pattern)]

            dates.append(day.isoformat())
            temp_max.append(daily_max)
            temp_min.append(daily_min)
            temp_mean.append(daily_mean)
            precipitation.append(precip)
            windspeed.append(wind)
            weather_codes.append(wcode)

        resolved_label = (
            location_name.strip()
            if location_name and location_name.strip()
            else f"Lat {lat:.4f}, Lon {lon:.4f}"
        )

        return {
            "latitude": lat,
            "longitude": lon,
            "elevation": 411.0,
            "timezone": timezone or "UTC",
            "current_weather": {
                "temperature": temp_mean[0],
                "windspeed": windspeed[0],
                "weathercode": weather_codes[0],
                "time": f"{dates[0]}T12:00",
            },
            "daily": {
                "time": dates,
                "weathercode": weather_codes,
                "temperature_2m_max": temp_max,
                "temperature_2m_min": temp_min,
                "temperature_2m_mean": temp_mean,
                "precipitation_sum": precipitation,
                "windspeed_10m_max": windspeed,
            },
            "daily_units": {
                "temperature_2m_max": "°C",
                "temperature_2m_min": "°C",
                "temperature_2m_mean": "°C",
                "precipitation_sum": "mm",
                "windspeed_10m_max": "km/h",
            },
            "metadata": {
                "location_name": resolved_label,
                "source": self.SOURCE_LABEL,
                "is_demo": True,
                "demo_notice": DEMO_NOTICE,
                "fetched_at": datetime.now(dt_timezone.utc).isoformat(),
            },
        }


def get_sample_weather_data(
    latitude: float = 11.0168,
    longitude: float = 76.9558,
    forecast_days: int = 7,
    location_name: str | None = None,
    start_date: date | None = None,
) -> dict[str, Any]:
    """Convenience function returning an offline demonstration weather payload."""
    return SampleWeatherProvider().get_weather_forecast(
        latitude=latitude,
        longitude=longitude,
        forecast_days=forecast_days,
        location_name=location_name,
        start_date=start_date,
    )
