"""Unit tests for APScheduler integration, job execution, and error handling."""

from __future__ import annotations

import pytest
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from app.exceptions import SchedulerError, ValidationError
from app.scheduler import ReportScheduler


def test_scheduler_initialization_triggers() -> None:
    daily_sched = ReportScheduler(job_callback=lambda: None, interval="daily", schedule_time="07:30")
    daily_sched.configure_job()
    jobs = daily_sched.get_jobs()
    assert len(jobs) == 1
    assert isinstance(jobs[0].trigger, CronTrigger)

    hourly_sched = ReportScheduler(job_callback=lambda: None, interval="hourly")
    hourly_sched.configure_job()
    assert isinstance(hourly_sched.get_jobs()[0].trigger, IntervalTrigger)

    minutes_sched = ReportScheduler(job_callback=lambda: None, interval="minutes", interval_minutes=15)
    minutes_sched.configure_job()
    assert isinstance(minutes_sched.get_jobs()[0].trigger, IntervalTrigger)


def test_scheduler_invalid_parameters() -> None:
    with pytest.raises(ValidationError):
        ReportScheduler(job_callback=lambda: None, interval="weekly")

    with pytest.raises(ValidationError):
        ReportScheduler(job_callback=lambda: None, interval="daily", schedule_time="25:99")

    with pytest.raises(SchedulerError):
        ReportScheduler(job_callback=lambda: None, interval="minutes", interval_minutes=0)


def test_scheduler_executes_bounded_job_and_shuts_down() -> None:
    executions: list[int] = []

    def _job() -> None:
        executions.append(1)

    scheduler = ReportScheduler(
        job_callback=_job,
        interval="daily",
        schedule_time="08:00",
        blocking=True,
    )
    scheduler.start(run_immediately=True, max_runs=1, interval_seconds_override=1)

    assert len(executions) == 1
    assert scheduler.run_count == 1
    assert scheduler.success_count == 1
    assert scheduler.failure_count == 0


def test_scheduler_handles_job_failure_without_crashing() -> None:
    attempts = 0

    def _flaky_job() -> None:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise RuntimeError("Simulated transient failure")

    scheduler = ReportScheduler(
        job_callback=_flaky_job,
        interval="minutes",
        interval_minutes=1,
        blocking=True,
    )
    scheduler.start(run_immediately=True, max_runs=2, interval_seconds_override=1)

    assert scheduler.run_count == 2
    assert scheduler.failure_count == 1
    assert scheduler.success_count == 1
    assert "Simulated transient failure" in (scheduler.last_error or "")
