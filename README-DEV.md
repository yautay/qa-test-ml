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

## Uruchomienie stacka Celery + external Redis (docker compose)

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

Local Redis (tylko auth, dev/test):
```bash
docker compose -f tools/runtime/docker-compose.yml --profile redis-auth --profile cpu up --build
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
- `IMAGE_BASE_DIR`, `COMPARE_TMP_DIR` (tmp musi być pod `IMAGE_BASE_DIR`)
- Redis wspólny dla API/Celery/JobStore:
  `REDIS_URL` albo `REDIS_HOST`, `REDIS_PORT`, `REDIS_DB`, `REDIS_USERNAME`, `REDIS_PASSWORD`, `REDIS_TLS`, oraz `REDIS_PREFIX`
- `CELERY_BROKER_URL`, `CELERY_RESULT_BACKEND` tylko gdy chcesz nadpisać wspólny Redis
- `COMPARE_QUEUE_CPU`, `COMPARE_QUEUE_GPU`, `ENABLE_GPU_QUEUE`, `COMPARE_EXECUTION_DEVICE`
- `CELERY_CPU_CONCURRENCY`, `CELERY_GPU_CONCURRENCY` (w `tools/runtime/.env`)
- `COMPARE_MAX_FILE_SIZE_BYTES`, `COMPARE_MAX_TOTAL_UPLOAD_BYTES`, `COMPARE_ALLOWED_IMAGE_FORMATS`
- `COMPARE_MAX_IMAGE_SIDE`, `COMPARE_MAX_IMAGE_PIXELS`
- `COMPARE_RATE_LIMIT_ENABLED`, `COMPARE_RATE_LIMIT_*`
- `PROMETHEUS_WORKER_*`, `PROMETHEUS_MULTIPROC_DIR` (ustaw na `/tmp/...`, nie w repo)
- `HMAC_ENABLED`, `HMAC_SECRET`, `HMAC_ALLOWED_SKEW_SEC`, `HMAC_REQUIRE_NONCE`, `HMAC_NONCE_TTL_SEC`

Bezpieczny snippet dla workerów (eliminuje błąd `Path is outside IMAGE_BASE_DIR`):

```env
IMAGE_BASE_DIR=.
COMPARE_TMP_DIR=.compare_tmp
```

Konfiguracja Redis:

- Priorytet: `REDIS_URL` > split vars (`REDIS_HOST`, `REDIS_PORT`, `REDIS_DB`, `REDIS_USERNAME`, `REDIS_PASSWORD`, `REDIS_TLS`) > domyślne wartości w kodzie.
- `REDIS_STARTUP_CHECK_MODE`: `ping` (domyślnie), `rw` (probe SET/GET/DEL pod `REDIS_PREFIX`), `none` (pomija check; używać ostrożnie).
- Jeśli `JOB_STORE_BACKEND=redis`, aplikacja wykona startup check Redis i zakończy start błędem przy niepoprawnej konfiguracji lub niedostępnym Redis.
- Logi startupowe pokazują tylko zamaskowany URL i flagi `*_configured`, bez jawnego hasła.

Przykłady:

```env
# URL mode
REDIS_URL=rediss://svc-user:svc-password@redis.example.com:6380/0

# Split vars mode
REDIS_URL=
REDIS_HOST=redis.example.com
REDIS_PORT=6380
REDIS_DB=0
REDIS_USERNAME=svc-user
REDIS_PASSWORD=svc-password
REDIS_TLS=true
```

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

Live Redis auth integration tests sa opt-in i nie wchodza do domyslnego `pytest -q`:

RUN_REDIS_INTEGRATION=1 PMS_REDIS_AUTH_URL='redis://:pms-secret@127.0.0.1:6380/0' pytest -q -m redis_integration tests/test_redis_auth_integration.py

Pelna instrukcja lokalnego setupu: `docs/testing-integration.md`.

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
