"""Application controller and command-line interface (CLI) for AutoReport."""

from __future__ import annotations

import argparse
import logging
import platform
import sys
from pathlib import Path
from typing import Sequence

from app import __app_name__, __version__
from app.api import WeatherAPIClient
from app.config import (
    AppConfig,
    validate_coordinates,
    validate_forecast_days,
    validate_schedule_interval,
    validate_schedule_time,
)
from app.data_processor import WeatherAnalytics, WeatherDataProcessor
from app.exceptions import (
    APIConnectionError,
    APIRateLimitError,
    APIResponseError,
    APITimeoutError,
    AutoReportError,
)
from app.logger import setup_logger
from app.pdf_generator import PDFReportGenerator
from app.sample_data import SampleWeatherProvider
from app.scheduler import ReportScheduler


def _print_banner() -> None:
    print("========================================")
    print("       AUTOREPORT AUTOMATION SYSTEM     ")
    print("========================================\n")


def _print_footer() -> None:
    print("\n========================================")


class AutoReportController:
    """Coordinates API retrieval, sample fallback, analytics, PDF rendering, and scheduling."""

    def __init__(
        self,
        config: AppConfig | None = None,
        logger: logging.Logger | None = None,
    ) -> None:
        self.config = config or AppConfig.from_env()
        self.config.ensure_directories()
        self.logger = logger or setup_logger(
            name="autoreport",
            log_file=self.config.log_file,
            log_level=self.config.log_level,
        )
        self.api_client = WeatherAPIClient(
            base_url=self.config.api_base_url,
            timeout=self.config.request_timeout,
            logger=self.logger,
        )
        self.sample_provider = SampleWeatherProvider()
        self.processor = WeatherDataProcessor(logger=self.logger)
        self.pdf_generator = PDFReportGenerator(
            reports_dir=self.config.reports_dir,
            charts_dir=self.config.charts_dir,
            logger=self.logger,
        )

    def generate_report(
        self,
        latitude: float | None = None,
        longitude: float | None = None,
        location_name: str | None = None,
        forecast_days: int | None = None,
        output_path: Path | None = None,
        demo: bool = False,
        allow_fallback: bool = False,
        save_data: bool = True,
        quiet: bool = False,
    ) -> tuple[Path, WeatherAnalytics]:
        """Execute the end-to-end report generation workflow."""
        lat = self.config.default_latitude if latitude is None else latitude
        lon = self.config.default_longitude if longitude is None else longitude
        lat, lon = validate_coordinates(lat, lon)

        days = self.config.forecast_days if forecast_days is None else forecast_days
        days = validate_forecast_days(days)

        resolved_location = location_name
        if resolved_location is None:
            if latitude is None and longitude is None:
                resolved_location = self.config.default_location_name
            else:
                resolved_location = f"Lat {lat:.4f}, Lon {lon:.4f}"

        def _say(msg: str) -> None:
            if not quiet:
                print(msg)

        if demo:
            _say("[WARN] Demonstration mode enabled. Using offline sample data (not real-time API data).")
            self.logger.warning("Generating report in offline demonstration mode.")
            payload = self.sample_provider.get_weather_forecast(
                latitude=lat,
                longitude=lon,
                forecast_days=days,
                location_name=resolved_location,
                timezone=self.config.timezone,
            )
            _say("[SUCCESS] Sample demonstration data loaded.")
        else:
            _say("[INFO] Connecting to weather API...")
            try:
                payload = self.api_client.fetch_weather_forecast(
                    latitude=lat,
                    longitude=lon,
                    forecast_days=days,
                    timezone=self.config.timezone,
                    location_name=resolved_location,
                )
                _say("[SUCCESS] Data retrieved successfully.")
            except (APIConnectionError, APITimeoutError, APIRateLimitError, APIResponseError) as exc:
                if not allow_fallback:
                    raise
                _say(f"[WARN] Live API unavailable: {exc}")
                _say("[WARN] Falling back to offline demonstration sample data (labeled as DEMO DATA).")
                self.logger.warning("API failed (%s); falling back to sample demonstration data.", exc)
                payload = self.sample_provider.get_weather_forecast(
                    latitude=lat,
                    longitude=lon,
                    forecast_days=days,
                    location_name=resolved_location,
                    timezone=self.config.timezone,
                )

        _say("[INFO] Processing weather information...")
        analytics = self.processor.process(payload)
        if save_data:
            self.processor.export_cleaned_data(analytics, self.config.data_dir)
        _say("[SUCCESS] Data processing completed.")

        _say("[INFO] Generating PDF report...")
        pdf_path = self.pdf_generator.generate_report(analytics, output_path=output_path)
        _say("[SUCCESS] PDF report generated.")
        _say(f"\nReport Location: {self._display_path(pdf_path)}")
        return pdf_path, analytics

    def _display_path(self, path: Path) -> str:
        try:
            return path.relative_to(self.config.base_dir).as_posix()
        except ValueError:
            return str(path)

    def run_scheduler(
        self,
        interval: str | None = None,
        schedule_time: str | None = None,
        interval_minutes: int | None = None,
        latitude: float | None = None,
        longitude: float | None = None,
        location_name: str | None = None,
        forecast_days: int | None = None,
        demo: bool = False,
        allow_fallback: bool = True,
        run_immediately: bool = False,
        max_runs: int | None = None,
        interval_seconds_override: int | None = None,
    ) -> ReportScheduler:
        """Start the automated APScheduler report runner."""
        chosen_interval = validate_schedule_interval(interval or self.config.schedule_interval)
        chosen_time = schedule_time or self.config.schedule_time
        validate_schedule_time(chosen_time)
        chosen_minutes = (
            interval_minutes if interval_minutes is not None else self.config.schedule_interval_minutes
        )

        def _scheduled_task() -> None:
            print(f"[INFO] Running scheduled report generation ({chosen_interval})...")
            self.generate_report(
                latitude=latitude,
                longitude=longitude,
                location_name=location_name,
                forecast_days=forecast_days,
                demo=demo,
                allow_fallback=allow_fallback,
                quiet=False,
            )

        scheduler = ReportScheduler(
            job_callback=_scheduled_task,
            interval=chosen_interval,
            schedule_time=chosen_time,
            interval_minutes=chosen_minutes,
            logger=self.logger,
            blocking=True,
        )

        print(f"[INFO] Scheduler configured: interval={chosen_interval}, time={chosen_time}, minutes={chosen_minutes}")
        if max_runs is not None:
            print(f"[INFO] Bounded execution active: will stop after {max_runs} run(s).")
        print("[INFO] Press Ctrl+C to stop the scheduler cleanly.\n")

        scheduler.start(
            run_immediately=run_immediately,
            max_runs=max_runs,
            interval_seconds_override=interval_seconds_override,
        )
        return scheduler

    def get_info(self) -> dict[str, str]:
        """Collect application metadata for the `info` command."""
        return {
            "Application": f"{__app_name__} – Enterprise PDF Report Automation System",
            "Version": __version__,
            "Python": platform.python_version(),
            "API Provider": f"Open-Meteo ({self.config.api_base_url})",
            "Default Location": (
                f"{self.config.default_location_name} "
                f"({self.config.default_latitude}, {self.config.default_longitude})"
            ),
            "Reports Directory": str(self.config.reports_dir),
            "Charts Directory": str(self.config.charts_dir),
            "Log File": str(self.config.log_file),
        }


def build_parser() -> argparse.ArgumentParser:
    """Construct the CLI argument parser with all supported subcommands."""
    parser = argparse.ArgumentParser(
        prog="autoreport",
        description="AutoReport – Enterprise PDF Report Automation System",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # generate subcommand
    gen_parser = subparsers.add_parser(
        "generate",
        help="Collect weather data, analyze trends, and generate a PDF report.",
    )
    gen_parser.add_argument("--latitude", type=float, default=None, help="Target latitude (-90 to 90)")
    gen_parser.add_argument("--longitude", type=float, default=None, help="Target longitude (-180 to 180)")
    gen_parser.add_argument("--location", type=str, default=None, help="Human-readable location label")
    gen_parser.add_argument("--days", type=int, default=None, help="Number of forecast days (1-16)")
    gen_parser.add_argument("--output", type=Path, default=None, help="Custom output PDF file path")
    gen_parser.add_argument(
        "--demo",
        action="store_true",
        help="Use offline demonstration sample data instead of calling the live API.",
    )
    gen_parser.add_argument(
        "--fallback",
        action="store_true",
        help="Automatically fall back to clearly labeled demo data if the live API fails.",
    )

    # schedule subcommand
    sched_parser = subparsers.add_parser(
        "schedule",
        help="Run automated report generation on a recurring schedule.",
    )
    sched_parser.add_argument(
        "--interval",
        type=str,
        choices=["daily", "hourly", "minutes"],
        default="daily",
        help="Scheduling interval mode (default: daily)",
    )
    sched_parser.add_argument(
        "--time",
        type=str,
        default=None,
        help="Daily execution time in 24-hour HH:MM format (default: 08:00)",
    )
    sched_parser.add_argument(
        "--minutes",
        type=int,
        default=None,
        help="Interval in minutes when --interval minutes is selected (default: 60)",
    )
    sched_parser.add_argument("--latitude", type=float, default=None, help="Target latitude (-90 to 90)")
    sched_parser.add_argument("--longitude", type=float, default=None, help="Target longitude (-180 to 180)")
    sched_parser.add_argument("--location", type=str, default=None, help="Human-readable location label")
    sched_parser.add_argument("--days", type=int, default=None, help="Number of forecast days (1-16)")
    sched_parser.add_argument(
        "--demo",
        action="store_true",
        help="Use offline demonstration sample data for scheduled runs.",
    )
    sched_parser.add_argument(
        "--no-fallback",
        action="store_true",
        help="Disable automatic fallback to demo data during scheduled runs if the API fails.",
    )
    sched_parser.add_argument(
        "--run-now",
        action="store_true",
        help="Execute one job immediately upon starting the scheduler.",
    )
    sched_parser.add_argument(
        "--max-runs",
        type=int,
        default=None,
        help="Stop gracefully after N scheduled executions (useful for verification).",
    )

    # info subcommand
    subparsers.add_parser(
        "info",
        help="Display application metadata and active directory paths.",
    )

    # validate subcommand
    subparsers.add_parser(
        "validate",
        help="Validate configuration parameters, coordinates, and workspace directories.",
    )

    return parser


def main(argv: Sequence[str] | None = None, config: AppConfig | None = None) -> int:
    """CLI entry point for AutoReport."""
    parser = build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)

    if args.command is None:
        parser.print_help()
        return 0

    _print_banner()

    try:
        active_config = config or AppConfig.from_env()
        active_config.validate()
        controller = AutoReportController(config=active_config)

        if args.command == "generate":
            controller.generate_report(
                latitude=args.latitude,
                longitude=args.longitude,
                location_name=args.location,
                forecast_days=args.days,
                output_path=args.output,
                demo=args.demo,
                allow_fallback=args.fallback,
            )
            _print_footer()
            return 0

        if args.command == "schedule":
            if args.max_runs is not None and args.max_runs < 1:
                print("[ERROR] --max-runs must be at least 1.")
                _print_footer()
                return 1
            controller.run_scheduler(
                interval=args.interval,
                schedule_time=args.time,
                interval_minutes=args.minutes,
                latitude=args.latitude,
                longitude=args.longitude,
                location_name=args.location,
                forecast_days=args.days,
                demo=args.demo,
                allow_fallback=not args.no_fallback,
                run_immediately=args.run_now,
                max_runs=args.max_runs,
            )
            _print_footer()
            return 0

        if args.command == "info":
            for key, value in controller.get_info().items():
                print(f"{key:<20}: {value}")
            _print_footer()
            return 0

        if args.command == "validate":
            checks = active_config.validate()
            print("[SUCCESS] Configuration is valid.\n")
            for check in checks:
                print(f"  - {check}")
            _print_footer()
            return 0

    except AutoReportError as exc:
        print(f"[ERROR] {exc}")
        if args.command == "generate" and isinstance(
            exc, (APIConnectionError, APITimeoutError, APIRateLimitError, APIResponseError)
        ):
            print("[INFO] Tip: Run with --demo for offline demonstration mode, or --fallback to auto-fallback.")
        _print_footer()
        return 1
    except Exception as exc:
        print(f"[ERROR] Unexpected application error: {exc}")
        _print_footer()
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
