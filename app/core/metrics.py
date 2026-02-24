from __future__ import annotations

from prometheus_client import Counter, Gauge, Histogram

jobs_submitted_total = Counter("pms_jobs_submitted_total", "Submitted compare jobs", ["metric"])
jobs_started_total = Counter("pms_jobs_started_total", "Started compare jobs", ["metric"])
jobs_finished_total = Counter("pms_jobs_finished_total", "Finished compare jobs", ["metric"])
jobs_failed_total = Counter("pms_jobs_failed_total", "Failed compare jobs", ["metric"])
jobs_inflight = Gauge("pms_jobs_inflight", "Inflight compare jobs")
job_duration_seconds = Histogram(
    "pms_job_duration_seconds",
    "Compare job duration in seconds",
    ["metric", "status"],
)
