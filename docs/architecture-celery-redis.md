# Celery + Redis Architecture

## Components

- API (`FastAPI`): accepts `POST /v1/compare/jobs`, reads status/results, exposes `/metrics`.
- Broker/Store (`Redis`): task broker for Celery and shared job state storage.
- Workers (`Celery`): execute LPIPS/DISTS calculations and heatmap generation.
- Monitoring (`Prometheus` + `Grafana`): collects and visualizes runtime metrics.

## Data Flow

1. Client calls `POST /v1/compare/jobs` with images.
2. API validates payload and creates a `queued` record in shared JobStore.
3. API enqueues Celery task to CPU or GPU queue.
4. Worker picks task, updates status to `running`, computes metrics.
5. Worker stores final state (`done` or `error`) and optional heatmap.
6. Client polls `GET /v1/compare/jobs/{id}` and gets consistent result from shared store, regardless of API instance.

## Why this removes cross-process inconsistency

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

## Metrics exposed by API

- `pms_jobs_submitted_total{metric}`
- `pms_jobs_started_total{metric}`
- `pms_jobs_finished_total{metric}`
- `pms_jobs_failed_total{metric}`
- `pms_jobs_inflight`
- `pms_job_duration_seconds{metric,status}`

## Developer Notes

- `CELERY_TASK_ALWAYS_EAGER=true` can be used in tests/local unit flow.
- For integration tests, use real Redis and run worker service.
- `JOB_STORE_BACKEND=memory` remains available for local debugging only.
