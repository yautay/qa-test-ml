# Perceptual Metrics Service

FastAPI service for perceptual similarity metrics ( comparing two images usingLPIPS, DISTS), with optional difference heatmaps.

## API Documentation

Interactive API documentation (Swagger UI): http://localhost:8080/docs  
ReDoc: http://localhost:8080/redoc  
OpenAPI Schema (JSON): http://localhost:8080/openapi.json

## Architecture

```
┌─────────────┐     ┌─────────────┐     ┌─────────────────┐
│   Client    │────▶│  FastAPI    │────▶│      Redis      │
│             │     │    API      │     │ (Broker + Store)│
└─────────────┘     └──────┬──────┘     └────────┬────────┘
                           │                      │
                           │              ┌───────▼───────┐
                           │              │               │
                    ┌──────▼──────┐       │    Celery      │
                    │  /health    │       │   Workers      │
                    │  /metrics   │       │  (CPU / GPU)   │
                    │  /v1/*      │       │               │
                    └─────────────┘       └───────────────┘
```

### Components

| Component | Technology | Purpose |
|-----------|------------|---------|
| API | FastAPI | Accepts jobs, reads status/results, exposes `/metrics` |
| Broker/Store | Redis | Task broker for Celery and shared job state storage |
| Workers | Celery | Execute LPIPS/DISTS calculations and heatmap generation |
| Monitoring | Prometheus + Grafana | Collects and visualizes runtime metrics |

### Supported Metrics

- **LPIPS** (Learned Perceptual Image Patch Similarity) - Networks: `alex`, `vgg`, `squeeze`
- **DISTS** (Deep Image Structure and Texture Similarity)

## How It Works

1. Client calls `POST /v1/compare/jobs` with two images
2. API validates payload and creates a `queued` record in Redis JobStore
3. API enqueues Celery task to CPU or GPU queue based on `COMPARE_EXECUTION_DEVICE`
4. Worker picks up task, updates status to `running`, computes metrics
5. Worker stores final state (`done` or `error`) and optional LPIPS heatmap
6. Client polls `GET /v1/compare/jobs/{id}` and gets consistent result from shared store

### Why Celery + Redis?

The previous implementation held job state in process memory. In multi-process mode, one process could not see jobs created in another process. Storing state in Redis ensures every API process reads the same source of truth.

## Requirements

- Python 3.12
- WSL2 / Linux / macOS
- virtualenv

## Setup

### 1. Create virtual environment

```bash
python -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
```

### 2. Install dependencies

```bash
# runtime
pip install -r requirements.txt

# development
pip install -r requirements-dev.txt
```

### 3. Optional: File-based configuration

```bash
cp config.toml.example config.toml
```

## Running the Application

### Development (local)

```bash
uvicorn app.main:app --reload
```

API available at: http://localhost:8080
Swagger UI: http://localhost:8080/docs
ReDoc: http://localhost:8080/redoc
OpenAPI Schema: http://localhost:8080/openapi.json

### Production (Docker Compose)

PyTorch 2.10+ automatically detects CPU/GPU at runtime. Use profiles to select worker type:

#### CPU workers (development/test)

```bash
docker compose -f tools/runtime/docker-compose.yml --profile cpu up --build
```

#### GPU workers (production)

Requires `nvidia-container-toolkit`:

```bash
docker compose -f tools/runtime/docker-compose.yml --profile gpu up --build
```

#### Both CPU and GPU workers

```bash
docker compose -f tools/runtime/docker-compose.yml --profile cpu --profile gpu up --build
```

### Monitoring Stack (optional)

```bash
docker compose -f tools/monitoring/docker-compose.yml up -d
```

| Service | URL |
|---------|-----|
| API | http://localhost:8080 |
| Metrics | http://localhost:8080/metrics |
| Worker CPU Metrics | http://localhost:9101/metrics |
| Worker GPU Metrics | http://localhost:9102/metrics |
| Prometheus | http://localhost:9090 |
| Grafana | http://localhost:3000 (admin/admin) |

Worker metrics exposure changes monitoring behavior:

- `pms-api` target still scrapes API counters (for example: submitted jobs).
- New `pms-worker-cpu` / `pms-worker-gpu` targets scrape Celery worker process metrics.
- Dashboards now read real execution metrics (`started/finished/failed/inflight/duration`) from worker targets instead of showing partial or zero values from API-only scraping.

## Configuration

Configuration priority (highest to lowest):
1. System environment variables
2. `config.toml` (project root, `[env]` section)
3. Hardcoded defaults in code

### Main Runtime Settings

| Variable | Default | Description |
|----------|---------|-------------|
| `JOB_STORE_BACKEND` | `redis` | Job storage: `redis` or `memory` |
| `REDIS_URL` | `redis://127.0.0.1:6379/0` | Redis connection |
| `COMPARE_TMP_DIR` | system temp dir | Directory for temporary uploaded images during job execution |
| `CELERY_BROKER_URL` | `redis://127.0.0.1:6379/0` | Celery broker URL |
| `CELERY_RESULT_BACKEND` | `redis://127.0.0.1:6379/0` | Celery result backend |
| `COMPARE_QUEUE_CPU` | `compare-cpu` | CPU worker queue name |
| `COMPARE_QUEUE_GPU` | `compare-gpu` | GPU worker queue name |
| `ENABLE_GPU_QUEUE` | `false` | Enable GPU queue |
| `COMPARE_EXECUTION_DEVICE` | `auto` | Device: `auto`, `cpu`, or `gpu` |
| `API_DEBUG` | `true` | Enable detailed error responses |
| `PROMETHEUS_WORKER_ENABLED` | `false` | Enables `/metrics` HTTP server inside Celery worker process; required to collect worker-side job execution metrics |
| `PROMETHEUS_WORKER_ADDR` | `0.0.0.0` | Bind address for worker metrics server (change if metrics must be localhost-only or restricted network scope) |
| `PROMETHEUS_WORKER_PORT` | `9101` | Port exposed by a worker for Prometheus scraping; each worker service must use a unique port |
| `PROMETHEUS_MULTIPROC_DIR` | (empty) | When set, enables prometheus-client multiprocess aggregation for prefork workers and stores shard files in this directory |

### Worker Sizing (DevOps Guide)

Recommended starting points for worker process settings:

| Variable | Recommended start | How to tune |
|----------|-------------------|-------------|
| `CELERY_CPU_CONCURRENCY` | `2` to `4` | Increase when CPU has headroom and queue latency grows; decrease when memory pressure or context-switch overhead grows |
| `CELERY_GPU_CONCURRENCY` | `1` (safe), `2` (typical on 24 GB VRAM) | Increase one step at a time only after confirming no OOM and stable p95 duration |

Operational rules:

- Use `1` GPU worker per physical GPU; scale worker count first when adding GPUs.
- Keep a unique `PROMETHEUS_WORKER_PORT` per worker service (`9101`, `9102`, ...).
- Set `PROMETHEUS_MULTIPROC_DIR` whenever prefork workers can spawn multiple processes.
- After each concurrency change, observe queue delay, `p95`, error ratio, and OOM/restart events before the next change.

### GPU Reference (Ampere Baseline)

Use this as a starting point, then validate with production traffic profile:

| GPU VRAM | Example class | `CELERY_GPU_CONCURRENCY` start | Typical upper bound |
|----------|---------------|-------------------------------|---------------------|
| 8 GB | RTX 3060 8GB | `1` | `1` |
| 10-12 GB | RTX 3080 10GB / RTX 3060 12GB | `1` | `2` (light workload only) |
| 16 GB | A4000 class | `1` | `2` |
| 24 GB | RTX 3090 / A5000 class | `2` | `3` |
| 48 GB | A6000 class | `3` | `4` |

Rollback signals (lower concurrency immediately):

- CUDA OOM errors or frequent worker restarts.
- Rising p95/p99 duration after concurrency increase.
- Error ratio increase without corresponding input quality changes.

### API Hardening Settings

| Variable | Default | Description |
|----------|---------|-------------|
| `COMPARE_MAX_FILE_SIZE_BYTES` | `10485760` | Max single uploaded image size in bytes |
| `COMPARE_MAX_TOTAL_UPLOAD_BYTES` | `20971520` | Max combined uploaded payload size in bytes |
| `COMPARE_ALLOWED_IMAGE_FORMATS` | `png,jpeg,webp` | Allowed image formats (comma-separated) |
| `COMPARE_MAX_IMAGE_SIDE` | `8192` | Max width/height allowed on upload |
| `COMPARE_MAX_IMAGE_PIXELS` | `40000000` | Max image pixels (`width * height`) |
| `COMPARE_RATE_LIMIT_ENABLED` | `false` | Enables in-memory request rate limiting on `/v1/compare/*` |
| `COMPARE_RATE_LIMIT_CREATE_LIMIT` | `60` | Max create-job requests per window per client |
| `COMPARE_RATE_LIMIT_CREATE_WINDOW_SEC` | `60` | Window size (seconds) for create-job rate limit |
| `COMPARE_RATE_LIMIT_READ_LIMIT` | `240` | Max read requests per window per client |
| `COMPARE_RATE_LIMIT_READ_WINDOW_SEC` | `60` | Window size (seconds) for read rate limit |

### Logging Settings

| Variable | Default | Description |
|----------|---------|-------------|
| `LOG_LEVEL` | `INFO` | Console log level |
| `LOG_API_ENABLED` | `false` | Enable API logging sink |
| `LOG_API_URL` | - | Target endpoint for POST log events |
| `LOG_API_LEVEL` | `ERROR` | API sink level threshold |
| `LOG_API_TIMEOUT_MS` | `2000` | API sink timeout (ms) |
| `LOG_API_TOKEN` | - | Bearer token for API auth (not logged) |
| `LOG_SERVICE_NAME` | `perceptual-metrics-service` | Service name in log payload |

## API Endpoints

Full API reference with request/response examples available via [Swagger UI](http://localhost:8080/docs).

## Metrics

Prometheus metrics exposed at `/metrics`:

| Metric | Description |
|--------|-------------|
| `pms_jobs_submitted_total{metric}` | Total jobs submitted |
| `pms_jobs_started_total{metric}` | Total jobs started |
| `pms_jobs_finished_total{metric}` | Total jobs finished |
| `pms_jobs_failed_total{metric}` | Total jobs failed |
| `pms_jobs_inflight` | Jobs currently processing |
| `pms_job_duration_seconds{metric,status}` | Job duration histogram |
| `pms_rejected_requests_total{endpoint,reason,status_code}` | Rejected compare API requests |

## Development

### Run Tests

```bash
pytest -q
```

### HMAC authentication (optional)

HMAC protects all `/v1/compare/*` endpoints when enabled. Public endpoints (`/health`, `/metrics`, docs) remain open.

Configuration:

- `HMAC_ENABLED` (`false` by default)
- `HMAC_SECRET` (required when enabled)
- `HMAC_ALLOWED_SKEW_SEC` (default `300`)
- `HMAC_REQUIRE_NONCE` (default `true`)
- `HMAC_NONCE_TTL_SEC` (default `300`)

Required headers when enabled:

- `X-HMAC-Timestamp` (unix epoch seconds)
- `X-HMAC-Nonce` (required when `HMAC_REQUIRE_NONCE=true`)
- `X-HMAC-Signature` (hex digest)

#### Signing contract

Canonical string is newline-separated and UTF-8 encoded:

```text
METHOD
PATH
query=<raw_query_string>
<signed_fields_sorted_lexicographically_as_key=value>
timestamp=<X-HMAC-Timestamp>
nonce=<X-HMAC-Nonce-or-dash-when-optional-and-empty>
```

Signature algorithm:

```text
hex(hmac_sha256(HMAC_SECRET, canonical_string))
```

Comparison is done with constant-time `hmac.compare_digest`.

#### Signed fields by endpoint

`POST /v1/compare/jobs` must sign:

- `job_id`, `pair_id`, `metric`, `model`, `normalize`
- `img_a_sha256`, `img_b_sha256` (SHA-256 hex of raw uploaded file bytes)

`GET /v1/compare/jobs`, `GET /v1/compare/jobs/{job_id}`, `GET /v1/compare/jobs/{job_id}/heatmap`, `GET /v1/compare/jobs/{job_id}/error`:

- no business fields are required
- `METHOD`, `PATH`, `query`, `timestamp`, `nonce` are still always signed

#### Replay and time validation

- Timestamp must be within `HMAC_ALLOWED_SKEW_SEC` from server time.
- Nonce is single-use within `HMAC_NONCE_TTL_SEC`.
- Reusing nonce returns `401`.
- Current nonce cache is per-process in memory (in multi-instance deployments use sticky routing or move nonce storage to shared Redis).

#### Failure modes

- `401 Missing header: ...` - required HMAC header not present.
- `401 Invalid HMAC timestamp` - timestamp is not an integer.
- `401 HMAC timestamp is outside allowed skew` - stale/future request.
- `401 Invalid HMAC signature` - mismatch in canonical input or secret.
- `401 HMAC nonce replay detected` - nonce already used in valid window.
- `503 HMAC is enabled but not configured` - runtime misconfiguration.

#### Integration notes

- Keep client clock synchronized (NTP).
- On retry, generate a new timestamp and nonce, then recompute signature.
- For multipart requests, hash the exact bytes sent for each file field.
- If `HMAC_ENABLED=true` and `HMAC_SECRET` is empty, app startup fails (fail-fast).

### Lint & Format

```bash
ruff check .
black .
```

### Type Check

```bash
mypy .
```

### Security Audit

```bash
pip-audit
```

### Full Check (before commit)

```bash
make full-check
```

## Choosing the Right Model

| Model | Speed | Accuracy | Recommended Use |
|-------|-------|----------|-----------------|
| `alex` | Fastest | Good | Quick comparisons, high-volume processing |
| `vgg` | Medium | Best | Precise perceptual matching, research |
| `squeeze` | Fast | Good | Balanced performance |
| `dists` | Slower | Excellent | Comprehensive quality assessment |

## Business Use Cases

- **Computer Vision Model Evaluation**: Compare GAN outputs, super-resolution results
- **A/B Testing**: Compare different image processing pipelines
- **Visual Regression Testing**: Detect unintended visual changes
- **Quality Assurance**: Verify compression, format conversion, watermarking effects

## Documentation

- Architecture details: `docs/architecture-celery-redis.md`
- Hardening roadmap (stage 1/2): `docs/hardening-roadmap.md`
- Runtime compose config: `tools/runtime/docker-compose.yml`
- Monitoring compose config: `tools/monitoring/docker-compose.yml`
