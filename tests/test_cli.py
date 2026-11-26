"""Unit and integration tests for the AutoReport CLI."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from app.exceptions import APIConnectionError
from app.main import main


def test_cli_help(capsys) -> None:
    with pytest.raises(SystemExit) as exc_info:
        main(["--help"])
    assert exc_info.value.code == 0
    out = capsys.readouterr().out
    assert "autoreport" in out
    assert "generate" in out
    assert "schedule" in out


def test_cli_info_and_validate(isolated_config, capsys) -> None:
    exit_info = main(["info"], config=isolated_config)
    assert exit_info == 0
    out_info = capsys.readouterr().out
    assert "AutoReport" in out_info
    assert "Open-Meteo" in out_info

    exit_val = main(["validate"], config=isolated_config)
    assert exit_val == 0
    out_val = capsys.readouterr().out
    assert "[SUCCESS] Configuration is valid." in out_val


def test_cli_generate_demo_mode(isolated_config, capsys) -> None:
    exit_code = main(
        ["generate", "--latitude", "13.0827", "--longitude", "80.2707", "--demo"],
        config=isolated_config,
    )
    assert exit_code == 0
    out = capsys.readouterr().out
    assert "Demonstration mode enabled" in out
    assert "[SUCCESS] PDF report generated." in out

    pdfs = list(isolated_config.reports_dir.glob("*.pdf"))
    assert len(pdfs) == 1
    assert isolated_config.log_file.exists()


def test_cli_generate_mocked_api_success(isolated_config, valid_api_payload, capsys) -> None:
    with patch("app.api.WeatherAPIClient.fetch_weather_forecast", return_value=valid_api_payload):
        exit_code = main(
            ["generate", "--latitude", "11.0168", "--longitude", "76.9558"],
            config=isolated_config,
        )

    assert exit_code == 0
    out = capsys.readouterr().out
    assert "[SUCCESS] Data retrieved successfully." in out
    assert "[SUCCESS] PDF report generated." in out
    assert len(list(isolated_config.reports_dir.glob("*.pdf"))) == 1


def test_cli_generate_api_failure_without_and_with_fallback(isolated_config, capsys) -> None:
    with patch(
        "app.api.WeatherAPIClient.fetch_weather_forecast",
        side_effect=APIConnectionError("Network unreachable"),
    ):
        fail_code = main(["generate"], config=isolated_config)
        fail_out = capsys.readouterr().out
        assert fail_code == 1
        assert "[ERROR] Network unreachable" in fail_out

        fallback_code = main(["generate", "--fallback"], config=isolated_config)
        fallback_out = capsys.readouterr().out
        assert fallback_code == 0
        assert "Falling back to offline demonstration sample data" in fallback_out
        assert "[SUCCESS] PDF report generated." in fallback_out


def test_cli_schedule_bounded_run(isolated_config, capsys) -> None:
    exit_code = main(
        ["schedule", "--interval", "daily", "--demo", "--run-now", "--max-runs", "1"],
        config=isolated_config,
    )
    assert exit_code == 0
    out = capsys.readouterr().out
    assert "Scheduler configured: interval=daily" in out
    assert "[SUCCESS] PDF report generated." in out
    assert len(list(isolated_config.reports_dir.glob("*.pdf"))) == 1
