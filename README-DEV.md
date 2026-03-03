# AI Corner

Projekt wewnętrzny oparty o FastAPI + Torch.

## Wymagania

- Python 3.12
- WSL2 / Linux / macOS
- virtualenv

---

## Setup

### 1. Utworzenie środowiska

python -m venv .venv
source .venv/bin/activate
pip install --upgrade pip

### 2. Instalacja zależności

# runtime
pip install -r requirements.txt

# dev
pip install -r requirements-dev.txt

---

## Uruchomienie aplikacji

uvicorn app.main:app --reload

## Uruchomienie stacka Celery + Redis (docker compose)

Przygotuj env:

cp tools/runtime/.env.example tools/runtime/.env

### CPU (domyślnie)

Używa `requirements.txt` z wersją CPU-only PyTorch (~200MB):
```bash
docker compose -f tools/runtime/docker-compose.yml up --build
```

### GPU (produkcja)

Wymaga `nvidia-container-toolkit`:
```bash
# Uruchom z profilem gpu:
docker compose -f tools/runtime/docker-compose.yml --profile gpu up --build
```

Monitoring (Prometheus + Grafana + redis exporter):

docker compose -f tools/monitoring/docker-compose.yml up -d

Adresy:

- API: http://localhost:8080
- Metrics: http://localhost:8080/metrics
- Prometheus: http://localhost:9090
- Grafana: http://localhost:3000 (admin/admin)

Opcjonalnie konfiguracja przez plik:

cp config.toml.example config.toml

Priorytet ustawień: zmienne systemowe > config.toml > domyślne wartości w kodzie.

Jak ustawiać zmienne:

- Systemowo (najwyższy priorytet), np. `export LOG_LEVEL=DEBUG`
- W `config.toml` w sekcji `[env]`, np. `LOG_LEVEL = "DEBUG"`
- Jeżeli nie ustawisz żadnej z powyższych, aplikacja bierze wartość domyślną z kodu

Główne ustawienia runtime:
- `JOB_STORE_BACKEND` (`redis` lub `memory`)
- `REDIS_URL`, `REDIS_PREFIX`, `COMPARE_TMP_DIR`
- `CELERY_BROKER_URL`, `CELERY_RESULT_BACKEND`
- `COMPARE_QUEUE_CPU`, `COMPARE_QUEUE_GPU`, `ENABLE_GPU_QUEUE`, `COMPARE_EXECUTION_DEVICE`
- `CELERY_CPU_CONCURRENCY`, `CELERY_GPU_CONCURRENCY` (w `tools/runtime/.env`)
- `COMPARE_MAX_FILE_SIZE_BYTES`, `COMPARE_MAX_TOTAL_UPLOAD_BYTES`, `COMPARE_ALLOWED_IMAGE_FORMATS`
- `COMPARE_MAX_IMAGE_SIDE`, `COMPARE_MAX_IMAGE_PIXELS`
- `COMPARE_RATE_LIMIT_ENABLED`, `COMPARE_RATE_LIMIT_*`
- `HMAC_ENABLED`, `HMAC_SECRET`, `HMAC_ALLOWED_SKEW_SEC`, `HMAC_REQUIRE_NONCE`, `HMAC_NONCE_TTL_SEC`

### HMAC - kontrakt integracyjny

Po wlaczeniu `HMAC_ENABLED=true` endpointy `/v1/compare/*` wymagaja naglowkow:

- `X-HMAC-Timestamp` (epoch sec)
- `X-HMAC-Nonce`
- `X-HMAC-Signature`

Podpis obejmuje zawsze: `METHOD`, `PATH`, `query`, `timestamp`, `nonce`.

Dla `POST /v1/compare/jobs` podpis obejmuje dodatkowo pola biznesowe:

- `job_id`, `pair_id`, `metric`, `model`, `normalize`
- `img_a_sha256`, `img_b_sha256` (hash z surowych bajtow plikow)

Kolejnosc pol: leksykograficzna po kluczu (`key=value`, jeden wpis na linie). Algorytm: `HMAC-SHA256`, wynik w hex.

---

## Testy

pytest -q

---

## Lint / Format

ruff check .
black .

---

## Typy

mypy .

---

## Audyt bezpieczeństwa

pip-audit

---

## Full check przed commitem

make full-check

---

## Struktura zależności

- `requirements.txt` – runtime (CPU-only, do dev/test)
- `requirements-dev.txt` – dev/test

---

- Używamy pre-commit
- Każdy commit powinien przechodzić make full-check

