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
| Prometheus | http://localhost:9090 |
| Grafana | http://localhost:3000 (admin/admin) |

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
| `CELERY_BROKER_URL` | `redis://127.0.0.1:6379/0` | Celery broker URL |
| `CELERY_RESULT_BACKEND` | `redis://127.0.0.1:6379/0` | Celery result backend |
| `COMPARE_QUEUE_CPU` | `compare-cpu` | CPU worker queue name |
| `COMPARE_QUEUE_GPU` | `compare-gpu` | GPU worker queue name |
| `ENABLE_GPU_QUEUE` | `false` | Enable GPU queue |
| `COMPARE_EXECUTION_DEVICE` | `auto` | Device: `auto`, `cpu`, or `gpu` |
| `API_DEBUG` | `true` | Enable detailed error responses |

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

## Development

### Run Tests

```bash
pytest -q
```

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
- Runtime compose config: `tools/runtime/docker-compose.yml`
- Monitoring compose config: `tools/monitoring/docker-compose.yml`
