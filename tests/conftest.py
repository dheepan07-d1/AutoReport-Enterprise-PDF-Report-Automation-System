"""Shared pytest fixtures for AutoReport unit and integration tests."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import pytest

from app.config import AppConfig
from app.logger import close_logger_handlers


@pytest.fixture()
def isolated_config(tmp_path: Path) -> AppConfig:
    """Provide an AppConfig isolated inside a temporary directory."""
    cfg = AppConfig(
        base_dir=tmp_path,
        log_level="DEBUG",
        default_latitude=11.0168,
        default_longitude=76.9558,
        default_location_name="Coimbatore, IN",
    )
    cfg.ensure_directories()
    yield cfg
    close_logger_handlers(logging.getLogger("autoreport"))


@pytest.fixture()
def valid_api_payload() -> dict[str, Any]:
    """Return a realistic mocked Open-Meteo API JSON payload."""
    return {
        "latitude": 11.0168,
        "longitude": 76.9558,
        "elevation": 411.0,
        "timezone": "Asia/Kolkata",
        "daily": {
            "time": [
                "2026-11-20",
                "2026-11-21",
                "2026-11-22",
                "2026-11-23",
                "2026-11-24",
            ],
            "temperature_2m_max": [31.2, 32.0, 30.5, 29.8, 31.6],
            "temperature_2m_min": [21.4, 22.1, 21.8, 20.9, 21.5],
            "temperature_2m_mean": [26.3, 27.05, 26.15, 25.35, 26.55],
            "precipitation_sum": [0.0, 1.2, 8.4, 0.0, 0.5],
            "windspeed_10m_max": [12.0, 14.5, 18.2, 11.0, 13.4],
            "weathercode": [0, 2, 63, 1, 2],
        },
        "metadata": {
            "location_name": "Coimbatore, IN",
            "source": "Open-Meteo Forecast REST API (api.open-meteo.com)",
            "is_demo": False,
            "demo_notice": "",
            "fetched_at": "2026-11-20T06:00:00Z",
        },
    }
