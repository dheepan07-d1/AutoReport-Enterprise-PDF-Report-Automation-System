"""Unit tests for data cleaning, missing-value handling, statistics, and sample data."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.data_processor import WeatherDataProcessor
from app.exceptions import DataProcessingError
from app.sample_data import SampleWeatherProvider


def test_process_valid_payload_statistics(valid_api_payload) -> None:
    processor = WeatherDataProcessor()
    analytics = processor.process(valid_api_payload)

    assert len(analytics.cleaned_df) == 5
    assert analytics.stats["days_count"] == 5
    assert analytics.stats["temp_min_overall"] == 20.9
    assert analytics.stats["temp_max_overall"] == 32.0
    assert analytics.stats["total_precipitation"] == 10.1
    assert analytics.stats["rainy_days_count"] == 3
    assert analytics.stats["warmest_date"] == "2026-11-21"
    assert analytics.stats["coolest_date"] == "2026-11-23"
    assert analytics.stats["wettest_date"] == "2026-11-22"
    assert analytics.stats["duplicates_removed"] == 0
    assert analytics.stats["missing_values_imputed"] == 0
    assert len(analytics.insights) >= 5


def test_process_handles_duplicates_missing_values_and_sorting() -> None:
    noisy_payload = {
        "latitude": 13.0827,
        "longitude": 80.2707,
        "timezone": "Asia/Kolkata",
        "daily": {
            # Unsorted + duplicate date + invalid date row + missing numeric values
            "time": ["2026-11-22", "2026-11-20", "2026-11-20", "bad-date", "2026-11-21"],
            "temperature_2m_max": [33.0, 31.0, 31.0, 29.0, None],
            "temperature_2m_min": [24.0, 22.0, 22.0, 20.0, 23.0],
            "temperature_2m_mean": [None, 26.5, 26.5, 24.5, None],
            "precipitation_sum": [2.5, None, 0.0, 1.0, -1.0],
            "windspeed_10m_max": [15.0, 12.0, 12.0, 10.0, None],
            "weathercode": [2, 0, 0, 1, None],
        },
        "metadata": {"location_name": "Chennai, IN", "is_demo": False},
    }

    processor = WeatherDataProcessor()
    analytics = processor.process(noisy_payload)

    df = analytics.cleaned_df
    assert len(df) == 3
    assert df["date"].dt.strftime("%Y-%m-%d").tolist() == [
        "2026-11-20",
        "2026-11-21",
        "2026-11-22",
    ]
    assert analytics.stats["invalid_dates_dropped"] == 1
    assert analytics.stats["duplicates_removed"] == 1
    assert analytics.stats["missing_values_imputed"] >= 4
    # Interpolated temp_max on 2026-11-21 between 31.0 and 33.0 -> 32.0
    assert df.loc[1, "temp_max"] == 32.0
    # Negative precipitation clipped to 0.0
    assert df.loc[1, "precipitation"] == 0.0
    assert not df.isna().any().any()


def test_process_empty_payload_raises() -> None:
    processor = WeatherDataProcessor()
    with pytest.raises(DataProcessingError):
        processor.process({"daily": {"time": []}})


def test_export_cleaned_data_creates_csv(valid_api_payload, tmp_path: Path) -> None:
    processor = WeatherDataProcessor()
    analytics = processor.process(valid_api_payload)
    csv_path = processor.export_cleaned_data(analytics, output_dir=tmp_path, filename="test_out.csv")

    assert csv_path.exists()
    content = csv_path.read_text(encoding="utf-8")
    assert "date,temp_max,temp_min" in content
    assert "2026-11-20" in content


def test_sample_weather_provider_marks_demo_data() -> None:
    provider = SampleWeatherProvider()
    payload = provider.get_weather_forecast(
        latitude=13.0827,
        longitude=80.2707,
        forecast_days=7,
        location_name="Chennai, IN",
    )

    assert payload["metadata"]["is_demo"] is True
    assert "Demonstration" in payload["metadata"]["source"]
    assert "DEMONSTRATION DATA ONLY" in payload["metadata"]["demo_notice"]
    assert len(payload["daily"]["time"]) == 7

    analytics = WeatherDataProcessor().process(payload)
    assert analytics.metadata["is_demo"] is True
    assert any("demonstration data" in item.lower() for item in analytics.insights)
