from __future__ import annotations

from pathlib import Path
from typing import Any

from app.core.config import get_bool, get_str


def _prometheus_enabled() -> bool:
    return get_bool("PROMETHEUS_ENABLED", default=False)


# ---------------------------------------------------------------------------
# No-op stubs — used when PROMETHEUS_ENABLED=false so that prometheus_client
# is never imported and callers don't need to change.
# ---------------------------------------------------------------------------

class _NoOpMetric:
    def labels(self, *_args: Any, **_kwargs: Any) -> "_NoOpMetric":
        return self

    def inc(self, *_args: Any, **_kwargs: Any) -> None:
        pass

    def dec(self, *_args: Any, **_kwargs: Any) -> None:
        pass

    def set(self, *_args: Any, **_kwargs: Any) -> None:
        pass

    def observe(self, *_args: Any, **_kwargs: Any) -> None:
        pass


# ---------------------------------------------------------------------------
# Actual metrics or stubs depending on PROMETHEUS_ENABLED
# ---------------------------------------------------------------------------

if _prometheus_enabled():
    from prometheus_client import Counter, Gauge, Histogram

    def _ensure_prometheus_multiproc_dir() -> None:
        multiproc_dir = get_str("PROMETHEUS_MULTIPROC_DIR", "").strip()
        if not multiproc_dir:
            return
        Path(multiproc_dir).mkdir(parents=True, exist_ok=True)

    _ensure_prometheus_multiproc_dir()

    jobs_submitted_total = Counter("pms_jobs_submitted_total", "Submitted compare jobs", ["metric"])
    jobs_started_total = Counter("pms_jobs_started_total", "Started compare jobs", ["metric"])
    jobs_finished_total = Counter("pms_jobs_finished_total", "Finished compare jobs", ["metric"])
    jobs_failed_total = Counter("pms_jobs_failed_total", "Failed compare jobs", ["metric"])
    jobs_inflight = Gauge("pms_jobs_inflight", "Inflight compare jobs", multiprocess_mode="livesum")
    job_duration_seconds = Histogram(
        "pms_job_duration_seconds",
        "Compare job duration in seconds",
        ["metric", "status"],
    )
    rejected_requests_total = Counter(
        "pms_rejected_requests_total",
        "Rejected API requests",
        ["endpoint", "reason", "status_code"],
    )

else:
    jobs_submitted_total = _NoOpMetric()
    jobs_started_total = _NoOpMetric()
    jobs_finished_total = _NoOpMetric()
    jobs_failed_total = _NoOpMetric()
    jobs_inflight = _NoOpMetric()
    job_duration_seconds = _NoOpMetric()
    rejected_requests_total = _NoOpMetric()
