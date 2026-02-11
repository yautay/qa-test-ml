# Perceptual Metrics Service / Serwis Metryk Percepcyjnych

FastAPI service for comparing two images using perceptual similarity metrics (LPIPS), with optional difference heatmaps.

Serwis FastAPI do porownywania dwoch obrazow przy uzyciu metryk percepcyjnych (LPIPS), z opcjonalnym generowaniem mapy roznic.

## English

### What it does

- Compares two images available on the server filesystem
- Returns a scalar distance score (`/compare`)
- Can return a PNG heatmap overlay (`/compare/heatmap`)

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

### API

Health:

```bash
curl http://127.0.0.1:8080/health
```

Compare (JSON -> JSON):

```bash
curl -sS -X POST "http://127.0.0.1:8080/compare" \
  -H "Content-Type: application/json" \
  -d '{
    "ref_path": "tests/assets/ref_1.png",
    "test_path": "tests/assets/test_1.png",
    "config": {
      "metric": "lpips",
      "net": "vgg",
      "force_device": null
    }
  }'
```


Heatmap (JSON -> image/png):

```bash
curl -sS -X POST "http://127.0.0.1:8080/compare/heatmap" \
  -H "Content-Type: application/json" \
  -d '{
    "ref_path": "tests/assets/ref_1.png",
    "test_path": "tests/assets/test_1.png",
    "config": {
      "metric": "lpips",
      "net": "vgg",
      "force_device": "cpu",
      "max_side": 1024,
      "overlay_on": "test",
      "alpha": 0.45
    }
  }' \
  --output lpips_heatmap.png
```

### Notes

- `ref_path`/`test_path` are paths on the server running the API (this service does not upload files).
- `ref_path`/`test_path` must resolve inside `IMAGE_BASE_DIR` (default: current working directory).
- GPU: you need a CUDA-enabled PyTorch build; then set `config.force_device` to `"cuda"`.
- `API_DEBUG=1` (default) returns a detailed JSON 500 response; set `API_DEBUG=0` to disable it.

### Metrics

- `lpips`: implemented (scalar + heatmap). Nets: `vgg`, `alex`, `squeeze`.
- `dists`: optional (scalar only). Heatmap is not supported.
