# Perceptual Metrics Service / Serwis Metryk Percepcyjnych

FastAPI service for comparing two images using perceptual similarity metrics (LPIPS), with optional difference heatmaps.

Serwis FastAPI do porownywania dwoch obrazow przy uzyciu metryk percepcyjnych (LPIPS), z opcjonalnym generowaniem mapy roznic.

## English

### What it does

- Compares two images available on the server filesystem
- Returns LPIPS + DISTS scores and LPIPS heatmap in one response (`/compare`)
- Supports dedicated endpoints for LPIPS (`/compare/lpips`) and DISTS (`/compare/dists`)

### Requirements

- Python + pip
- Packages from `requirements.txt` (includes `fastapi`, `uvicorn`, `torch`, `lpips`, `pillow`)

### Install

```bash
pip install -r requirements.txt
```

### Tests

```bash
pip install -r requirements.txt -r requirements-dev.txt
pytest
```

### Run

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8080
```

Open Swagger UI:

- `http://127.0.0.1:8080/docs`

OpenAPI JSON:

- `http://127.0.0.1:8080/openapi.json`
- `http://127.0.0.1:8080/redoc`

### API

Health:

```bash
curl http://127.0.0.1:8080/health
```

Compare all (JSON -> JSON):

```bash
curl -sS -X POST "http://127.0.0.1:8080/compare" \
  -H "Content-Type: application/json" \
  -d '{
    "ref_path": "tests/assets/ref_1.png",
    "test_path": "tests/assets/test_1.png",
    "config": {
      "lpips_net": "vgg",
      "force_device": null,
      "max_side": 1024,
      "overlay_on": "test",
      "alpha": 0.45
    }
  }'
```


LPIPS only (JSON -> JSON):

```bash
curl -sS -X POST "http://127.0.0.1:8080/compare/lpips" \
  -H "Content-Type: application/json" \
  -d '{
    "ref_path": "tests/assets/ref_1.png",
    "test_path": "tests/assets/test_1.png",
    "config": {
      "net": "vgg",
      "force_device": null,
      "max_side": 1024,
      "overlay_on": "test",
      "alpha": 0.45
    }
  }'
```

DISTS only (JSON -> JSON):

```bash
curl -sS -X POST "http://127.0.0.1:8080/compare/dists" \
  -H "Content-Type: application/json" \
  -d '{
    "ref_path": "tests/assets/ref_1.png",
    "test_path": "tests/assets/test_1.png",
    "config": {
      "force_device": null
    }
  }'
```

Create async comparison job (multipart/form-data):

```bash
curl -sS -X POST "http://127.0.0.1:8080/v1/compare/jobs" \
  -F "job_id=8ebf6dad-bf45-4f7d-a267-4bcf7a7d66ea" \
  -F "pair_id=pair_001" \
  -F "metric=both" \
  -F "model=alex" \
  -F "normalize=true" \
  -F "img_a=@tests/assets/ref_1.png" \
  -F "img_b=@tests/assets/test_1.png"
```

Get async job status:

```bash
curl -sS "http://127.0.0.1:8080/v1/compare/jobs/8ebf6dad-bf45-4f7d-a267-4bcf7a7d66ea"
```

List all async jobs:

```bash
curl -sS "http://127.0.0.1:8080/v1/compare/jobs"
```

Download heatmap PNG for completed job:

```bash
curl -sS "http://127.0.0.1:8080/v1/compare/jobs/8ebf6dad-bf45-4f7d-a267-4bcf7a7d66ea/heatmap" -o heatmap.png
```

### Notes

- `ref_path`/`test_path` are paths on the server running the API (this service does not upload files).
- `ref_path`/`test_path` must resolve inside `IMAGE_BASE_DIR` (default: current working directory).
- GPU: you need a CUDA-enabled PyTorch build; then set `config.force_device` to `"cuda"`.
- `API_DEBUG=1` (default) returns a detailed JSON 500 response; set `API_DEBUG=0` to disable it.
- `/v1/compare/jobs` keeps job state in memory (no persistence after process restart).
- Heatmap endpoint is available only for completed jobs with `metric=lpips` or `metric=both`.

### Logging (Loguru)

The service uses `loguru` with two sinks:

- Console sink (always enabled)
- API sink (optional, disabled by default)

Environment variables:

- `LOG_LEVEL` - console log level (default: `INFO`)
- `LOG_API_ENABLED` - enable API sink (`true`/`false`, default: `false`)
- `LOG_API_URL` - target endpoint for `POST` log events
- `LOG_API_LEVEL` - API sink level threshold (default: `ERROR`)
- `LOG_API_TIMEOUT_MS` - API sink timeout in milliseconds (default: `2000`)
- `LOG_API_TOKEN` - optional bearer token for API sink auth
- `LOG_SERVICE_NAME` - `service` field in log payload (default: `perceptual-metrics-service`)

API sink payload shape:

- `timestamp`, `level`, `message`, `service`, `module`, `function`, `line`, `exception`, `extra`

### Metrics

- `lpips`: implemented (scalar + heatmap). Nets: `vgg`, `alex`, `squeeze`.
- `dists`: implemented for scalar scoring.
