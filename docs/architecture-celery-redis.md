# Celery + Redis Architecture

## Components

- API (`FastAPI`): accepts `POST /v1/compare/jobs`, reads status/results, exposes `/metrics`.
- Broker/Store (`Redis`): task broker for Celery and shared job state storage.
- Workers (`Celery`): execute LPIPS/DISTS calculations and heatmap generation.
- Monitoring (`Prometheus` + `Grafana`): collects and visualizes runtime metrics.
- Redis jobs index is garbage-collected automatically using TTL-based score pruning.

## Data Flow

1. Client calls `POST /v1/compare/jobs` with images.
2. API validates payload and creates a `queued` record in shared JobStore.
3. API enqueues Celery task to CPU or GPU queue.
4. Worker picks task, updates status to `running`, computes metrics.
5. Worker stores final state (`done` or `error`) and optional heatmap.
6. Client polls `GET /v1/compare/jobs/{id}` and gets consistent result from shared store, regardless of API instance.


The previous implementation held job state in process memory. In multi-process mode, one process could not see jobs created in another process. The current implementation stores state in Redis, so every API process reads the same source of truth.

## Queue Strategy

- CPU queue: `COMPARE_QUEUE_CPU` (default `compare-cpu`).
- GPU queue: `COMPARE_QUEUE_GPU` (default `compare-gpu`).
- Selection controlled by:
  - `ENABLE_GPU_QUEUE`
  - `COMPARE_EXECUTION_DEVICE` (`auto|cpu|gpu`)

## Error Handling

- LPIPS heatmap failures are logged as `CRITICAL`.
- Job is marked as `error` with user-facing message:
  - `LPIPS heatmap generation failed. Please verify image dimensions/content and retry.`

## Request Authentication (optional HMAC)

- Controlled by runtime flags: `HMAC_ENABLED`, `HMAC_SECRET`, `HMAC_ALLOWED_SKEW_SEC`, `HMAC_REQUIRE_NONCE`, `HMAC_NONCE_TTL_SEC`.
- Scope: all `/v1/compare/*` endpoints.
- Public endpoints (`/health`, `/metrics`, docs) remain unsigned for observability.
- HMAC contract signs method/path/query/timestamp/nonce and, for job creation, business fields + uploaded file SHA-256 values.
- Replay protection uses nonce cache with TTL (current implementation: per-process memory).

## Metrics Topology

Metrics are produced in two places and should be scraped from both:

- API `/metrics` target:
  - `pms_jobs_submitted_total{metric}`
  - `pms_rejected_requests_total{endpoint,reason,status_code}`
- Celery worker `/metrics` targets:
  - `pms_jobs_started_total{metric}`
  - `pms_jobs_finished_total{metric}`
  - `pms_jobs_failed_total{metric}`
  - `pms_jobs_inflight`
  - `pms_job_duration_seconds{metric,status}`

If Prometheus scrapes only API metrics, execution panels can show partial or zero values even when jobs are running.

## Capacity Playbook (DevOps)

### CPU workers

- Start with `CELERY_CPU_CONCURRENCY=2..4` per host.
- Increase by `+1` when CPU utilization and memory are stable but queue latency grows.
- Decrease when host memory pressure, swap, or context-switch overhead appears.

### GPU workers

- Run one worker service per physical GPU.
- Start with `CELERY_GPU_CONCURRENCY=1` (`2` is typical for 24 GB VRAM cards such as RTX 3090/A5000).
- Increase by `+1` only after verifying stable VRAM usage, no CUDA OOM, and stable p95 duration.

### Ampere reference values

- 8 GB VRAM: start `1`, max `1`.
- 10-12 GB VRAM: start `1`, max `2` for light workloads.
- 16 GB VRAM: start `1`, max `2`.
- 24 GB VRAM: start `2`, max `3`.
- 48 GB VRAM: start `3`, max `4`.

### Monitoring after each change

- Verify Prometheus targets for API and all worker metrics endpoints are `UP`.
- Track `p95/p99` duration, error ratio, inflight jobs, and worker restart/OOM events for at least one load window.
- Roll back one step immediately on sustained OOM or rising tail latency.

