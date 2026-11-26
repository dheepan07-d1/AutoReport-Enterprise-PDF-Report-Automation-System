"""Unit tests for chart generation and PDF report generation."""

from __future__ import annotations

from pathlib import Path

import pdfplumber
import pytest

from app.data_processor import WeatherDataProcessor
from app.exceptions import PDFGenerationError
from app.pdf_generator import PDFReportGenerator
from app.sample_data import SampleWeatherProvider


def test_generate_pdf_report_creates_valid_pdf_and_charts(valid_api_payload, tmp_path: Path) -> None:
    reports_dir = tmp_path / "reports"
    charts_dir = tmp_path / "charts"

    analytics = WeatherDataProcessor().process(valid_api_payload)
    generator = PDFReportGenerator(reports_dir=reports_dir, charts_dir=charts_dir)

    pdf_path = generator.generate_report(analytics)

    assert pdf_path.exists()
    assert pdf_path.parent == reports_dir
    assert pdf_path.stat().st_size > 10_000

    # Verify PDF header signature
    with pdf_path.open("rb") as f:
        assert f.read(5) == b"%PDF-"

    # Verify 3 chart PNG files were created
    chart_files = list(charts_dir.glob("*.png"))
    assert len(chart_files) == 3
    for chart in chart_files:
        assert chart.stat().st_size > 1_000

    # Extract text with pdfplumber to verify required report sections and page numbers
    with pdfplumber.open(pdf_path) as pdf:
        assert len(pdf.pages) >= 2
        full_text = "\n".join(page.extract_text() or "" for page in pdf.pages)

    assert "AUTOREPORT" in full_text
    assert "Coimbatore, IN" in full_text
    assert "Open-Meteo Forecast REST API" in full_text
    assert "Executive Weather Summary" in full_text
    assert "Temperature & Precipitation Statistics" in full_text
    assert "Daily Weather Breakdown" in full_text
    assert "Graphical Visualizations" in full_text
    assert "Analytical Summary & Key Insights" in full_text
    assert "Page 1 of" in full_text


def test_generate_demo_pdf_contains_demo_warning(tmp_path: Path) -> None:
    payload = SampleWeatherProvider().get_weather_forecast(
        latitude=13.0827,
        longitude=80.2707,
        location_name="Chennai Demo",
    )
    analytics = WeatherDataProcessor().process(payload)
    generator = PDFReportGenerator(
        reports_dir=tmp_path / "reports",
        charts_dir=tmp_path / "charts",
    )

    pdf_path = generator.generate_report(analytics, output_path=tmp_path / "reports" / "demo.pdf")
    assert pdf_path.exists()

    with pdfplumber.open(pdf_path) as pdf:
        first_page_text = pdf.pages[0].extract_text() or ""

    assert "OFFLINE DEMONSTRATION MODE" in first_page_text
    assert "DEMONSTRATION DATA ONLY" in first_page_text


def test_generate_pdf_raises_on_invalid_output_target(valid_api_payload, tmp_path: Path) -> None:
    analytics = WeatherDataProcessor().process(valid_api_payload)
    bad_charts_file = tmp_path / "not_a_dir"
    bad_charts_file.write_text("file", encoding="utf-8")

    generator = PDFReportGenerator(
        reports_dir=tmp_path / "reports",
        charts_dir=bad_charts_file,
    )
    with pytest.raises(PDFGenerationError):
        generator.generate_report(analytics)
