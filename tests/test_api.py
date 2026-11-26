"""Unit tests for REST API integration and failure handling."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
import requests

from app.api import WeatherAPIClient
from app.exceptions import (
    APIConnectionError,
    APIRateLimitError,
    APIResponseError,
    APITimeoutError,
    ValidationError,
)


def _mock_response(status_code: int = 200, json_data=None, json_exc: Exception | None = None, text: str = ""):
    response = MagicMock()
    response.status_code = status_code
    response.text = text
    if json_exc is not None:
        response.json.side_effect = json_exc
    else:
        response.json.return_value = json_data
    return response


def test_fetch_weather_forecast_success(valid_api_payload) -> None:
    session = MagicMock(spec=requests.Session)
    session.get.return_value = _mock_response(status_code=200, json_data=valid_api_payload)

    client = WeatherAPIClient(timeout=10.0, session=session)
    result = client.fetch_weather_forecast(
        latitude=11.0168,
        longitude=76.9558,
        forecast_days=5,
        location_name="Coimbatore, IN",
    )

    assert result["metadata"]["is_demo"] is False
    assert result["metadata"]["location_name"] == "Coimbatore, IN"
    assert len(result["daily"]["time"]) == 5
    session.get.assert_called_once()
    _, kwargs = session.get.call_args
    assert kwargs["timeout"] == 10.0
    assert kwargs["params"]["latitude"] == 11.0168


def test_fetch_weather_forecast_timeout() -> None:
    session = MagicMock(spec=requests.Session)
    session.get.side_effect = requests.exceptions.Timeout("timed out")

    client = WeatherAPIClient(timeout=5.0, session=session)
    with pytest.raises(APITimeoutError, match="timed out"):
        client.fetch_weather_forecast(11.0168, 76.9558)


def test_fetch_weather_forecast_connection_error() -> None:
    session = MagicMock(spec=requests.Session)
    session.get.side_effect = requests.exceptions.ConnectionError("DNS error")

    client = WeatherAPIClient(session=session)
    with pytest.raises(APIConnectionError, match="Unable to connect"):
        client.fetch_weather_forecast(11.0168, 76.9558)


def test_fetch_weather_forecast_rate_limit() -> None:
    session = MagicMock(spec=requests.Session)
    session.get.return_value = _mock_response(status_code=429, text="Too Many Requests")

    client = WeatherAPIClient(session=session)
    with pytest.raises(APIRateLimitError, match="429"):
        client.fetch_weather_forecast(11.0168, 76.9558)


def test_fetch_weather_forecast_http_500() -> None:
    session = MagicMock(spec=requests.Session)
    session.get.return_value = _mock_response(status_code=500, text="Internal Server Error")

    client = WeatherAPIClient(session=session)
    with pytest.raises(APIResponseError, match="HTTP 500"):
        client.fetch_weather_forecast(11.0168, 76.9558)


def test_fetch_weather_forecast_invalid_json() -> None:
    session = MagicMock(spec=requests.Session)
    session.get.return_value = _mock_response(status_code=200, json_exc=ValueError("Invalid JSON"))

    client = WeatherAPIClient(session=session)
    with pytest.raises(APIResponseError, match="malformed JSON"):
        client.fetch_weather_forecast(11.0168, 76.9558)


def test_fetch_weather_forecast_missing_daily_section() -> None:
    session = MagicMock(spec=requests.Session)
    session.get.return_value = _mock_response(status_code=200, json_data={"latitude": 11.0})

    client = WeatherAPIClient(session=session)
    with pytest.raises(APIResponseError, match="missing the 'daily'"):
        client.fetch_weather_forecast(11.0168, 76.9558)


def test_fetch_weather_forecast_length_mismatch() -> None:
    session = MagicMock(spec=requests.Session)
    session.get.return_value = _mock_response(
        status_code=200,
        json_data={
            "daily": {
                "time": ["2026-11-20", "2026-11-21"],
                "temperature_2m_max": [30.0],
                "temperature_2m_min": [20.0, 21.0],
            }
        },
    )

    client = WeatherAPIClient(session=session)
    with pytest.raises(APIResponseError, match="length mismatch"):
        client.fetch_weather_forecast(11.0168, 76.9558)


@pytest.mark.parametrize("lat,lon", [(95.0, 76.0), (-91.0, 10.0), (11.0, 190.0), (11.0, -181.0)])
def test_fetch_weather_forecast_invalid_coordinates(lat: float, lon: float) -> None:
    client = WeatherAPIClient(session=MagicMock(spec=requests.Session))
    with pytest.raises(ValidationError):
        client.fetch_weather_forecast(lat, lon)
