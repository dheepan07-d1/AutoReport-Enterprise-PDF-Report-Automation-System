"""Automated report scheduling powered by APScheduler."""

from __future__ import annotations

import logging
import signal
from datetime import datetime
from typing import Callable

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from app.config import validate_schedule_interval, validate_schedule_time
from app.exceptions import SchedulerError


class ReportScheduler:
    """Manages scheduled automated report generation with error handling and clean shutdown."""

    def __init__(
        self,
        job_callback: Callable[[], object],
        interval: str = "daily",
        schedule_time: str = "08:00",
        interval_minutes: int = 60,
        logger: logging.Logger | None = None,
        blocking: bool = True,
    ) -> None:
        self.job_callback = job_callback
        self.interval = validate_schedule_interval(interval)
        self.schedule_time = schedule_time
        self.hour, self.minute = validate_schedule_time(schedule_time)
        if interval_minutes < 1:
            raise SchedulerError(f"interval_minutes must be >= 1 (got {interval_minutes}).")
        self.interval_minutes = interval_minutes
        self.logger = logger or logging.getLogger("autoreport.scheduler")
        self.blocking = blocking

        self.run_count = 0
        self.success_count = 0
        self.failure_count = 0
        self.last_error: str | None = None

        self._scheduler = (
            BlockingScheduler() if blocking else BackgroundScheduler()
        )
        self._job_id = "autoreport_scheduled_job"

    def build_trigger(self, interval_seconds_override: int | None = None):
        """Construct the APScheduler trigger corresponding to the configured schedule."""
        if interval_seconds_override is not None:
            if interval_seconds_override < 1:
                raise SchedulerError("interval_seconds_override must be >= 1.")
            return IntervalTrigger(seconds=interval_seconds_override)

        if self.interval == "daily":
            return CronTrigger(hour=self.hour, minute=self.minute)
        if self.interval == "hourly":
            return IntervalTrigger(hours=1)
        return IntervalTrigger(minutes=self.interval_minutes)

    def _execute_job(self, max_runs: int | None = None) -> None:
        """Execute one scheduled report generation run safely."""
        self.run_count += 1
        self.logger.info("Scheduled job #%d started.", self.run_count)
        try:
            self.job_callback()
            self.success_count += 1
            self.logger.info("Scheduled job #%d completed successfully.", self.run_count)
        except Exception as exc:
            self.failure_count += 1
            self.last_error = str(exc)
            self.logger.exception("Scheduled job #%d failed: %s", self.run_count, exc)
        finally:
            if max_runs is not None and self.run_count >= max_runs:
                self.logger.info(
                    "Reached max_runs=%d; initiating graceful scheduler shutdown.", max_runs
                )
                self.shutdown()

    def configure_job(
        self,
        run_immediately: bool = False,
        max_runs: int | None = None,
        interval_seconds_override: int | None = None,
    ) -> None:
        """Register the report generation job on the APScheduler instance."""
        trigger = self.build_trigger(interval_seconds_override=interval_seconds_override)
        next_run = datetime.now() if run_immediately else None

        job_kwargs = {
            "func": self._execute_job,
            "trigger": trigger,
            "id": self._job_id,
            "name": f"AutoReport ({self.interval})",
            "replace_existing": True,
            "max_instances": 1,
            "kwargs": {"max_runs": max_runs},
        }
        if next_run is not None:
            job_kwargs["next_run_time"] = next_run

        self._scheduler.add_job(**job_kwargs)
        self.logger.info(
            "Configured scheduler job '%s' (interval=%s, time=%s, minutes=%d, run_immediately=%s).",
            self._job_id,
            self.interval,
            self.schedule_time,
            self.interval_minutes,
            run_immediately,
        )

    def get_jobs(self):
        """Return registered APScheduler jobs."""
        return self._scheduler.get_jobs()

    def start(
        self,
        run_immediately: bool = False,
        max_runs: int | None = None,
        interval_seconds_override: int | None = None,
    ) -> None:
        """Start the scheduler and handle shutdown signals gracefully."""
        if not self.get_jobs():
            self.configure_job(
                run_immediately=run_immediately,
                max_runs=max_runs,
                interval_seconds_override=interval_seconds_override,
            )

        def _handle_signal(signum, _frame) -> None:  # pragma: no cover - OS signal handler
            self.logger.info("Received signal %s; shutting down scheduler.", signum)
            self.shutdown()

        previous_sigint = signal.getsignal(signal.SIGINT)
        try:
            signal.signal(signal.SIGINT, _handle_signal)
        except ValueError:
            # signal.signal can only be set from the main thread.
            previous_sigint = None

        self.logger.info("Starting APScheduler (blocking=%s).", self.blocking)
        try:
            self._scheduler.start()
        except (KeyboardInterrupt, SystemExit):
            self.logger.info("Scheduler interrupted by user; shutting down gracefully.")
            self.shutdown()
        except Exception as exc:
            self.logger.error("Scheduler encountered a fatal error: %s", exc)
            raise SchedulerError(f"Scheduler execution failed: {exc}") from exc
        finally:
            if previous_sigint is not None:
                try:
                    signal.signal(signal.SIGINT, previous_sigint)
                except ValueError:
                    pass

    def shutdown(self) -> None:
        """Gracefully stop the scheduler if it is currently running."""
        if self._scheduler.running:
            self._scheduler.shutdown(wait=False)
            self.logger.info("Scheduler stopped cleanly.")
