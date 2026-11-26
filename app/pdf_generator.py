"""Matplotlib visualization and ReportLab PDF report generation."""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.pdfgen import canvas
from reportlab.platypus import (
    Image,
    KeepTogether,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from app.data_processor import WeatherAnalytics
from app.exceptions import PDFGenerationError


class NumberedCanvas(canvas.Canvas):
    """ReportLab Canvas subclass that renders 'Page X of Y' and a consistent footer."""

    def __init__(self, *args: Any, footer_text: str = "", **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._saved_page_states: list[dict[str, Any]] = []
        self._footer_text = footer_text

    def showPage(self) -> None:
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self) -> None:
        total_pages = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self._draw_page_chrome(total_pages)
            super().showPage()
        super().save()

    def _draw_page_chrome(self, total_pages: int) -> None:
        page_width, _ = A4
        self.saveState()
        self.setStrokeColor(colors.HexColor("#CBD5E1"))
        self.setLineWidth(0.6)
        self.line(0.65 * inch, 0.58 * inch, page_width - 0.65 * inch, 0.58 * inch)

        self.setFont("Helvetica", 8)
        self.setFillColor(colors.HexColor("#475569"))
        self.drawString(0.65 * inch, 0.40 * inch, self._footer_text)
        self.drawRightString(
            page_width - 0.65 * inch,
            0.40 * inch,
            f"Page {self._pageNumber} of {total_pages}",
        )
        self.restoreState()


class ChartGenerator:
    """Creates high-resolution Matplotlib charts for embedding in PDF reports."""

    def __init__(self, charts_dir: Path, logger: logging.Logger | None = None) -> None:
        self.charts_dir = charts_dir
        self.logger = logger or logging.getLogger("autoreport.charts")

    def generate_all_charts(
        self, analytics: WeatherAnalytics, run_tag: str | None = None
    ) -> dict[str, Path]:
        """Generate temperature trend, min/max comparison, and precipitation charts."""
        try:
            self.charts_dir.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise PDFGenerationError(
                f"Cannot create charts directory '{self.charts_dir}': {exc}"
            ) from exc

        tag = run_tag or datetime.now().strftime("%Y%m%d_%H%M%S")
        df = analytics.cleaned_df
        date_labels = df["date"].dt.strftime("%b %d").tolist()
        is_demo = bool(analytics.metadata.get("is_demo", False))
        suffix = " [DEMO DATA]" if is_demo else ""

        charts = {
            "temperature_trend": self._create_temperature_trend_chart(
                df, date_labels, self.charts_dir / f"temperature_trend_{tag}.png", suffix
            ),
            "temp_comparison": self._create_temp_comparison_chart(
                df, date_labels, self.charts_dir / f"temp_comparison_{tag}.png", suffix
            ),
            "precipitation": self._create_precipitation_chart(
                df, date_labels, self.charts_dir / f"precipitation_{tag}.png", suffix
            ),
        }
        self.logger.info("Generated %d visualization chart(s) in %s", len(charts), self.charts_dir)
        return charts

    def _create_temperature_trend_chart(
        self, df: Any, date_labels: list[str], output_path: Path, title_suffix: str
    ) -> Path:
        fig, ax = plt.subplots(figsize=(8.2, 3.8), dpi=160)
        try:
            x = np.arange(len(date_labels))
            t_max = df["temp_max"].to_numpy(dtype=float)
            t_mean = df["temp_mean"].to_numpy(dtype=float)
            t_min = df["temp_min"].to_numpy(dtype=float)

            ax.fill_between(x, t_min, t_max, color="#93C5FD", alpha=0.28, label="Daily Range")
            ax.plot(x, t_max, marker="o", linewidth=2.0, color="#DC2626", label="Max Temp (°C)")
            ax.plot(x, t_mean, marker="s", linewidth=2.2, color="#1D4ED8", label="Mean Temp (°C)")
            ax.plot(x, t_min, marker="o", linewidth=2.0, color="#0284C7", label="Min Temp (°C)")

            for idx, val in enumerate(t_mean):
                ax.annotate(
                    f"{val:.1f}°",
                    (x[idx], val),
                    textcoords="offset points",
                    xytext=(0, 7),
                    ha="center",
                    fontsize=7.5,
                    color="#1E3A8A",
                )

            ax.set_title(f"Daily Temperature Trend{title_suffix}", fontsize=11.5, fontweight="bold", pad=10)
            ax.set_xlabel("Date", fontsize=9.5)
            ax.set_ylabel("Temperature (°C)", fontsize=9.5)
            ax.set_xticks(x)
            ax.set_xticklabels(date_labels, rotation=25 if len(date_labels) > 7 else 0, fontsize=8.5)
            ax.grid(True, linestyle="--", alpha=0.45)
            ax.legend(loc="best", frameon=True, fontsize=8.5)
            fig.tight_layout()
            fig.savefig(output_path, dpi=160)
            return output_path
        except Exception as exc:
            raise PDFGenerationError(f"Failed to render temperature trend chart: {exc}") from exc
        finally:
            plt.close(fig)

    def _create_temp_comparison_chart(
        self, df: Any, date_labels: list[str], output_path: Path, title_suffix: str
    ) -> Path:
        fig, ax = plt.subplots(figsize=(8.2, 3.8), dpi=160)
        try:
            x = np.arange(len(date_labels))
            width = 0.36
            t_max = df["temp_max"].to_numpy(dtype=float)
            t_min = df["temp_min"].to_numpy(dtype=float)

            bars_max = ax.bar(x - width / 2, t_max, width, label="Max Temp (°C)", color="#EF4444", alpha=0.88)
            bars_min = ax.bar(x + width / 2, t_min, width, label="Min Temp (°C)", color="#3B82F6", alpha=0.88)

            for bar in bars_max:
                h = bar.get_height()
                ax.text(
                    bar.get_x() + bar.get_width() / 2,
                    h + 0.3,
                    f"{h:.1f}",
                    ha="center",
                    va="bottom",
                    fontsize=7,
                    color="#7F1D1D",
                )
            for bar in bars_min:
                h = bar.get_height()
                ax.text(
                    bar.get_x() + bar.get_width() / 2,
                    h + 0.3,
                    f"{h:.1f}",
                    ha="center",
                    va="bottom",
                    fontsize=7,
                    color="#1E3A8A",
                )

            ax.set_title(
                f"Maximum vs. Minimum Temperature Comparison{title_suffix}",
                fontsize=11.5,
                fontweight="bold",
                pad=10,
            )
            ax.set_xlabel("Date", fontsize=9.5)
            ax.set_ylabel("Temperature (°C)", fontsize=9.5)
            ax.set_xticks(x)
            ax.set_xticklabels(date_labels, rotation=25 if len(date_labels) > 7 else 0, fontsize=8.5)
            y_top = max(float(np.max(t_max)), 0.0) + 4.0
            y_bottom = min(float(np.min(t_min)) - 2.0, 0.0)
            ax.set_ylim(y_bottom, y_top)
            ax.grid(True, axis="y", linestyle="--", alpha=0.45)
            ax.legend(loc="best", frameon=True, fontsize=8.5)
            fig.tight_layout()
            fig.savefig(output_path, dpi=160)
            return output_path
        except Exception as exc:
            raise PDFGenerationError(f"Failed to render temperature comparison chart: {exc}") from exc
        finally:
            plt.close(fig)

    def _create_precipitation_chart(
        self, df: Any, date_labels: list[str], output_path: Path, title_suffix: str
    ) -> Path:
        fig, ax = plt.subplots(figsize=(8.2, 3.6), dpi=160)
        try:
            x = np.arange(len(date_labels))
            precip = df["precipitation"].to_numpy(dtype=float)
            avg_precip = float(np.mean(precip))

            bars = ax.bar(x, precip, width=0.52, color="#0EA5E9", alpha=0.88, label="Precipitation (mm)")
            ax.axhline(
                avg_precip,
                color="#0F172A",
                linestyle="--",
                linewidth=1.3,
                label=f"Daily Average ({avg_precip:.2f} mm)",
            )

            for bar in bars:
                h = bar.get_height()
                ax.text(
                    bar.get_x() + bar.get_width() / 2,
                    h + max(0.15, float(np.max(precip)) * 0.02),
                    f"{h:.1f}",
                    ha="center",
                    va="bottom",
                    fontsize=7.5,
                    color="#0C4A6E",
                )

            ax.set_title(f"Daily Precipitation Forecast{title_suffix}", fontsize=11.5, fontweight="bold", pad=10)
            ax.set_xlabel("Date", fontsize=9.5)
            ax.set_ylabel("Precipitation (mm)", fontsize=9.5)
            ax.set_xticks(x)
            ax.set_xticklabels(date_labels, rotation=25 if len(date_labels) > 7 else 0, fontsize=8.5)
            ax.set_ylim(0, max(float(np.max(precip)) * 1.22, 2.0))
            ax.grid(True, axis="y", linestyle="--", alpha=0.45)
            ax.legend(loc="best", frameon=True, fontsize=8.5)
            fig.tight_layout()
            fig.savefig(output_path, dpi=160)
            return output_path
        except Exception as exc:
            raise PDFGenerationError(f"Failed to render precipitation chart: {exc}") from exc
        finally:
            plt.close(fig)


class PDFReportGenerator:
    """Generates enterprise-grade PDF weather reports using ReportLab."""

    def __init__(
        self,
        reports_dir: Path,
        charts_dir: Path,
        logger: logging.Logger | None = None,
    ) -> None:
        self.reports_dir = reports_dir
        self.charts_dir = charts_dir
        self.logger = logger or logging.getLogger("autoreport.pdf")
        self.chart_generator = ChartGenerator(charts_dir=charts_dir, logger=self.logger)

    def generate_report(
        self,
        analytics: WeatherAnalytics,
        output_path: Path | None = None,
    ) -> Path:
        """Build charts and compile the complete PDF report.

        Args:
            analytics: Processed weather analytics object.
            output_path: Optional explicit output PDF path.

        Returns:
            Path to the generated PDF file.

        Raises:
            PDFGenerationError: If chart rendering or PDF writing fails.
        """
        now = datetime.now()
        run_tag = now.strftime("%Y%m%d_%H%M%S")
        generated_display = now.strftime("%Y-%m-%d %H:%M:%S")

        if output_path is not None:
            pdf_path = Path(output_path)
        else:
            prefix = "weather_demo_report" if analytics.metadata.get("is_demo") else "weather_report"
            pdf_path = self.reports_dir / f"{prefix}_{run_tag}.pdf"

        try:
            pdf_path.parent.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise PDFGenerationError(
                f"Cannot create output directory '{pdf_path.parent}': {exc}"
            ) from exc

        charts = self.chart_generator.generate_all_charts(analytics, run_tag=run_tag)

        styles = self._build_styles()
        story = self._build_story(analytics, charts, generated_display, styles)
        footer_text = f"AutoReport Enterprise Automation System  |  Generated {generated_display}"

        try:
            doc = SimpleDocTemplate(
                str(pdf_path),
                pagesize=A4,
                leftMargin=0.65 * inch,
                rightMargin=0.65 * inch,
                topMargin=0.65 * inch,
                bottomMargin=0.75 * inch,
                title="AutoReport – Enterprise Weather Analytics Report",
                author="AutoReport Automation System",
            )
            doc.build(
                story,
                canvasmaker=lambda *args, **kwargs: NumberedCanvas(
                    *args, footer_text=footer_text, **kwargs
                ),
            )
        except Exception as exc:
            self.logger.error("PDF generation failed for '%s': %s", pdf_path, exc)
            raise PDFGenerationError(f"Failed to build PDF report '{pdf_path}': {exc}") from exc

        if not pdf_path.exists() or pdf_path.stat().st_size == 0:
            raise PDFGenerationError(f"Generated PDF '{pdf_path}' is missing or empty.")

        self.logger.info("PDF report generated successfully: %s (%d bytes)", pdf_path, pdf_path.stat().st_size)
        return pdf_path

    @staticmethod
    def _build_styles() -> dict[str, ParagraphStyle]:
        base = getSampleStyleSheet()
        return {
            "title": ParagraphStyle(
                "ReportTitle",
                parent=base["Title"],
                fontName="Helvetica-Bold",
                fontSize=20,
                leading=24,
                textColor=colors.white,
                alignment=0,
            ),
            "subtitle": ParagraphStyle(
                "ReportSubtitle",
                parent=base["Normal"],
                fontName="Helvetica",
                fontSize=10,
                leading=14,
                textColor=colors.HexColor("#DBEAFE"),
            ),
            "section": ParagraphStyle(
                "SectionHeading",
                parent=base["Heading2"],
                fontName="Helvetica-Bold",
                fontSize=13,
                leading=17,
                textColor=colors.HexColor("#0F172A"),
                spaceBefore=12,
                spaceAfter=6,
            ),
            "body": ParagraphStyle(
                "BodyTextCustom",
                parent=base["Normal"],
                fontName="Helvetica",
                fontSize=9.5,
                leading=14,
                textColor=colors.HexColor("#1E293B"),
            ),
            "caption": ParagraphStyle(
                "ChartCaption",
                parent=base["Normal"],
                fontName="Helvetica-Oblique",
                fontSize=8.5,
                leading=12,
                textColor=colors.HexColor("#475569"),
                alignment=1,
            ),
            "warn": ParagraphStyle(
                "DemoWarning",
                parent=base["Normal"],
                fontName="Helvetica-Bold",
                fontSize=9.5,
                leading=13,
                textColor=colors.HexColor("#7C2D12"),
            ),
        }

    def _build_story(
        self,
        analytics: WeatherAnalytics,
        charts: dict[str, Path],
        generated_display: str,
        styles: dict[str, ParagraphStyle],
    ) -> list[Any]:
        meta = analytics.metadata
        stats = analytics.stats
        df = analytics.cleaned_df
        content_width = A4[0] - 1.3 * inch

        story: list[Any] = []

        # 1. Report Title Banner
        banner_title = "AUTOREPORT – ENTERPRISE WEATHER ANALYTICS REPORT"
        if meta.get("is_demo"):
            banner_subtitle = "Automated Meteorological Intelligence Report [OFFLINE DEMONSTRATION MODE]"
        else:
            banner_subtitle = "Automated Meteorological Intelligence & Forecast Report"

        banner = Table(
            [[Paragraph(banner_title, styles["title"])], [Paragraph(banner_subtitle, styles["subtitle"])]],
            colWidths=[content_width],
        )
        banner.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#0F172A")),
                    ("LEFTPADDING", (0, 0), (-1, -1), 14),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 14),
                    ("TOPPADDING", (0, 0), (0, 0), 14),
                    ("BOTTOMPADDING", (0, 1), (0, 1), 14),
                ]
            )
        )
        story.append(banner)
        story.append(Spacer(1, 10))

        # Offline Demonstration Warning Banner when applicable
        if meta.get("is_demo"):
            demo_box = Table(
                [[Paragraph(f"WARNING: {meta.get('demo_notice')}", styles["warn"])]],
                colWidths=[content_width],
            )
            demo_box.setStyle(
                TableStyle(
                    [
                        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#FEF3C7")),
                        ("BOX", (0, 0), (-1, -1), 1.0, colors.HexColor("#D97706")),
                        ("LEFTPADDING", (0, 0), (-1, -1), 10),
                        ("RIGHTPADDING", (0, 0), (-1, -1), 10),
                        ("TOPPADDING", (0, 0), (-1, -1), 8),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
                    ]
                )
            )
            story.append(demo_box)
            story.append(Spacer(1, 10))

        # 2, 3, 4. Metadata: Generation Date/Time, Selected Location, Data Source Information
        lat_str = f"{meta['latitude']:.4f}" if meta.get("latitude") is not None else "N/A"
        lon_str = f"{meta['longitude']:.4f}" if meta.get("longitude") is not None else "N/A"
        elev_str = f"{meta['elevation']:.1f} m" if meta.get("elevation") is not None else "N/A"

        meta_rows = [
            ["Generation Date & Time", generated_display, "Forecast Window", f"{meta.get('date_range')} ({stats['days_count']} days)"],
            ["Selected Location", str(meta.get("location_name")), "Coordinates (Lat, Lon)", f"{lat_str}, {lon_str}"],
            ["Data Source", str(meta.get("source")), "Timezone / Elevation", f"{meta.get('timezone')} / {elev_str}"],
        ]
        meta_table = Table(
            meta_rows,
            colWidths=[content_width * 0.22, content_width * 0.28, content_width * 0.22, content_width * 0.28],
        )
        meta_table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#F1F5F9")),
                    ("BACKGROUND", (2, 0), (2, -1), colors.HexColor("#F1F5F9")),
                    ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                    ("FONTNAME", (2, 0), (2, -1), "Helvetica-Bold"),
                    ("FONTNAME", (1, 0), (1, -1), "Helvetica"),
                    ("FONTNAME", (3, 0), (3, -1), "Helvetica"),
                    ("FONTSIZE", (0, 0), (-1, -1), 8.5),
                    ("TEXTCOLOR", (0, 0), (-1, -1), colors.HexColor("#0F172A")),
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("TOPPADDING", (0, 0), (-1, -1), 5),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                    ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ]
            )
        )
        story.append(meta_table)
        story.append(Spacer(1, 10))

        # 5. Weather Summary
        story.append(Paragraph("1. Executive Weather Summary", styles["section"]))
        summary_text = (
            f"This report analyzes {stats['days_count']} days of weather data for "
            f"<b>{meta.get('location_name')}</b> ({lat_str}, {lon_str}) covering {meta.get('date_range')}. "
            f"Across the forecast horizon, daily mean temperatures average <b>{stats['temp_mean_overall']:.1f} °C</b> "
            f"(ranging from a minimum of <b>{stats['temp_min_overall']:.1f} °C</b> to a peak of "
            f"<b>{stats['temp_max_overall']:.1f} °C</b>). Total cumulative precipitation is "
            f"<b>{stats['total_precipitation']:.1f} mm</b> over {stats['rainy_days_count']} rainy day(s), "
            f"with peak wind speeds reaching <b>{stats['max_wind_speed']:.1f} km/h</b>."
        )
        story.append(Paragraph(summary_text, styles["body"]))
        story.append(Spacer(1, 8))

        kpi_table = Table(
            [
                ["Mean Temperature", "Overall Min / Max", "Total Precipitation", "Max Wind Speed"],
                [
                    f"{stats['temp_mean_overall']:.1f} °C",
                    f"{stats['temp_min_overall']:.1f} / {stats['temp_max_overall']:.1f} °C",
                    f"{stats['total_precipitation']:.1f} mm",
                    f"{stats['max_wind_speed']:.1f} km/h",
                ],
            ],
            colWidths=[content_width / 4.0] * 4,
        )
        kpi_table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1E3A8A")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("FONTSIZE", (0, 0), (-1, 0), 8.5),
                    ("BACKGROUND", (0, 1), (-1, 1), colors.HexColor("#EFF6FF")),
                    ("TEXTCOLOR", (0, 1), (-1, 1), colors.HexColor("#0F172A")),
                    ("FONTNAME", (0, 1), (-1, 1), "Helvetica-Bold"),
                    ("FONTSIZE", (0, 1), (-1, 1), 11),
                    ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#93C5FD")),
                    ("TOPPADDING", (0, 0), (-1, -1), 6),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ]
            )
        )
        story.append(kpi_table)
        story.append(Spacer(1, 10))

        # 6. Temperature & Data Quality Statistics
        story.append(Paragraph("2. Temperature & Precipitation Statistics", styles["section"]))
        stat_rows = [
            ["Metric", "Value", "Metric", "Value"],
            ["Minimum Temperature", f"{stats['temp_min_overall']:.2f} °C", "Maximum Temperature", f"{stats['temp_max_overall']:.2f} °C"],
            ["Mean Temperature", f"{stats['temp_mean_overall']:.2f} °C", "Median Temperature", f"{stats['temp_median_overall']:.2f} °C"],
            ["Temperature Std Dev", f"{stats['temp_std_dev']:.2f} °C", "Avg Diurnal Range", f"{stats['avg_diurnal_range']:.2f} °C"],
            ["Avg Daily High", f"{stats['avg_daily_high']:.2f} °C", "Avg Daily Low", f"{stats['avg_daily_low']:.2f} °C"],
            ["Warmest Day", f"{stats['warmest_date']} ({stats['warmest_temp']:.1f} °C)", "Coolest Day", f"{stats['coolest_date']} ({stats['coolest_temp']:.1f} °C)"],
            ["Total Precipitation", f"{stats['total_precipitation']:.2f} mm", "Wettest Day", f"{stats['wettest_date']} ({stats['wettest_precip']:.1f} mm)"],
            ["Avg Wind Speed", f"{stats['avg_wind_speed']:.2f} km/h", "Temp Trend Slope", f"{stats['temp_trend_slope']:+.3f} °C/day"],
            ["Duplicates Removed", str(stats["duplicates_removed"]), "Missing Values Imputed", str(stats["missing_values_imputed"])],
        ]
        stat_table = Table(
            stat_rows,
            colWidths=[content_width * 0.25] * 4,
        )
        stat_table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0F172A")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("FONTNAME", (0, 1), (0, -1), "Helvetica-Bold"),
                    ("FONTNAME", (2, 1), (2, -1), "Helvetica-Bold"),
                    ("FONTSIZE", (0, 0), (-1, -1), 8.5),
                    ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F8FAFC")]),
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
                    ("TOPPADDING", (0, 0), (-1, -1), 4.5),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 4.5),
                    ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ]
            )
        )
        story.append(stat_table)
        story.append(Spacer(1, 10))

        # 7. Daily Weather Information
        story.append(Paragraph("3. Daily Weather Breakdown", styles["section"]))
        daily_rows = [["Date", "Condition", "Min (°C)", "Max (°C)", "Mean (°C)", "Precip (mm)", "Wind (km/h)"]]
        for _, row in df.iterrows():
            daily_rows.append(
                [
                    row["date"].strftime("%Y-%m-%d"),
                    str(row["weather_description"]),
                    f"{row['temp_min']:.1f}",
                    f"{row['temp_max']:.1f}",
                    f"{row['temp_mean']:.1f}",
                    f"{row['precipitation']:.1f}",
                    f"{row['wind_speed_max']:.1f}",
                ]
            )

        daily_table = Table(
            daily_rows,
            colWidths=[
                content_width * 0.14,
                content_width * 0.26,
                content_width * 0.11,
                content_width * 0.11,
                content_width * 0.12,
                content_width * 0.13,
                content_width * 0.13,
            ],
            repeatRows=1,
        )
        daily_table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1E293B")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
                    ("FONTSIZE", (0, 0), (-1, -1), 8.2),
                    ("ALIGN", (2, 0), (-1, -1), "RIGHT"),
                    ("ALIGN", (0, 0), (1, -1), "LEFT"),
                    ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F8FAFC")]),
                    ("GRID", (0, 0), (-1, -1), 0.45, colors.HexColor("#CBD5E1")),
                    ("TOPPADDING", (0, 0), (-1, -1), 4),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                    ("LEFTPADDING", (0, 0), (-1, -1), 5),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                ]
            )
        )
        story.append(daily_table)
        story.append(PageBreak())

        # 8. Graphical Visualizations
        story.append(Paragraph("4. Graphical Visualizations", styles["section"]))

        chart_specs = [
            ("temperature_trend", "Figure 1: Daily Temperature Trend (Min, Mean, and Max with Diurnal Band)", 3.15 * inch),
            ("temp_comparison", "Figure 2: Daily Maximum vs. Minimum Temperature Comparison", 3.15 * inch),
            ("precipitation", "Figure 3: Daily Precipitation Forecast vs. Period Average", 3.0 * inch),
        ]
        for key, caption, img_height in chart_specs:
            chart_img = Image(str(charts[key]), width=content_width, height=img_height)
            block = KeepTogether([chart_img, Spacer(1, 3), Paragraph(caption, styles["caption"]), Spacer(1, 10)])
            story.append(block)

        # 9. Summary and Insights
        story.append(Paragraph("5. Analytical Summary & Key Insights", styles["section"]))
        for idx, insight in enumerate(analytics.insights, start=1):
            story.append(Paragraph(f"{idx}. {insight}", styles["body"]))
            story.append(Spacer(1, 4))

        return story
