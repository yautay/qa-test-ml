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

Configuration source priority for runtime settings:

- system environment variables
- `config.toml` in project root (`[env]` section)
- hardcoded defaults in code

To start with file-based config, copy and edit:

```bash
cp config.toml.example config.toml
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
- Async jobs worker pool can be tuned with:
  - `COMPARE_JOB_WORKERS` (default: `2`)
  - `QUEUE_MAXSIZE` (default: `0`, means unbounded queue)
- Validation rules:
  - `COMPARE_JOB_WORKERS` is clamped to `1..(CPU_COUNT * 4)`
  - `QUEUE_MAXSIZE` lower bound is `0`
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

## Business Value / Wartość Biznesowa

### Supported Models

This API provides image similarity assessment using two perceptual metrics:

#### LPIPS (Learned Perceptual Image Patch Similarity)
- **Networks**: `alex`, `vgg`, `squeeze`
- **How it works**: Uses pre-trained convolutional neural networks (AlexNet, VGG, SqueezeNet) as feature extractors to measure perceptual similarity between images
- **Best for**: General-purpose perceptual comparison, GAN evaluation, image generation quality assessment

#### DISTS (Deep Image Structure and Texture Similarity)
- **Model**: DISTS (CNN-based)
- **How it works**: Combines deep features with structural and textural components to evaluate image quality
- **Best for**: More nuanced image quality assessment capturing both structure and texture differences

### Business Benefits

| Benefit | Description |
|---------|-------------|
| **Automated Quality Control** | Replace manual image comparison with objective, reproducible metrics |
| **Faster QA Processes** | Instantly compare thousands of images without human intervention |
| **Consistent Standards** | Ensure consistent quality standards across all visual content |
| **Cost Reduction** | Reduce time and resources spent on manual review |
| **Data-Driven Decisions** | Quantify visual effects, support metric-based decisions |

### Use Cases

- **Computer Vision Model Evaluation**: Compare GAN outputs, super-resolution results, or image restoration quality
- **A/B Testing**: Compare different image processing pipelines or rendering engines
- **Visual Regression Testing**: Detect unintended visual changes in UI/frontend updates
- **Content Moderation**: Identify visual similarities between images
- **Quality Assurance**: Verify image compression, format conversion, or watermarking effects

### Choosing the Right Model

| Model | Speed | Accuracy | Recommended Use |
|-------|-------|----------|-----------------|
| `alex` | Fastest | Good | Quick comparisons, high-volume processing |
| `vgg` | Medium | Best | Precise perceptual matching, research |
| `squeeze` | Fast | Good | Balanced performance |
| `dists` | Slower | Excellent | Comprehensive quality assessment |

---

### Obsługiwane modele

Ten API umożliwia ocenę podobieństwa obrazów przy użyciu dwóch metryk percepcyjnych:

#### LPIPS (Learned Perceptual Image Patch Similarity)
- **Sieci**: `alex`, `vgg`, `squeeze`
- **Jak działa**: Wykorzystuje wstępnie wytrenowane splotowe sieci neuronowe (AlexNet, VGG, SqueezeNet) jako ekstraktory cech do pomiaru podobieństwa percepcyjnego między obrazami
- **Najlepsze do**: Ogólnego porównywania percepcyjnego, ewaluacji GAN, oceny jakości generowanych obrazów

#### DISTS (Deep Image Structure and Texture Similarity)
- **Model**: DISTS (oparty na CNN)
- **Jak działa**: Łączy cechy głębokie ze składowymi strukturalnymi i teksturalnymi w celu oceny jakości obrazu
- **Najlepsze do**: Bardziej szczegółowej oceny jakości obrazu, uwzględniającej różnice w strukturze i teksturze

### Korzyści biznesowe

| Korzyść | Opis |
|---------|------|
| **Automatyczna kontrola jakości** | Zastąpienie ręcznego porównywania obrazów obiektywnymi, powtarzalnymi metrykami |
| **Szybsze procesy QA** | Natychmiastowe porównywanie tysięcy obrazów bez interwencji człowieka |
| **Spójne standardy** | Zapewnienie jednolitych standardów jakości dla wszystkich treści wizualnych |
| **Redukcja kosztów** | Zmniejszenie czasu i zasobów poświęcanych na ręczne przeglądy |
| **Decyzje oparte na danych** | Kwantyfikacja efektów wizualnych, wspieranie decyzji opartych na metrykach |

### Przypadki użycia

- **Ewaluacja modeli Computer Vision**: Porównywanie wyników GAN, super-rozdzielczości lub jakości przywracania obrazów
- **Testy A/B**: Porównywanie różnych potoków przetwarzania obrazów lub silników renderowania
- **Testy regresji wizualnej**: Wykrywanie niezamierzonych zmian wizualnych w aktualizacjach UI/frontend
- **Moderacja treści**: Identyfikowanie podobieństw wizualnych między obrazami
- **Zapewnienie jakości**: Weryfikacja efektów kompresji, konwersji formatów lub znaków wodnych

### Wybór odpowiedniego modelu

| Model | Szybkość | Dokładność | Zalecane użycie |
|-------|----------|------------|-----------------|
| `alex` | Najszybsza | Dobra | Szybkie porównania, przetwarzanie dużych wolumenów |
| `vgg` | Średnia | Najlepsza | Precyzyjne dopasowanie percepcyjne, badania |
| `squeeze` | Szybka | Dobra | Zrównoważona wydajność |
| `dists` | Wolniejsza | Wyborna | Kompleksowa ocena jakości |
