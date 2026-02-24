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

Wymaga `nvidia-container-toolkit` i używa pełnego PyTorch z CUDA (~3GB):
```bash
# Najpierw podmień requirements na GPU:
cp requirements.prod.txt requirements.txt

# Potem uruchom z profilem gpu:
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
- `REDIS_URL`, `REDIS_PREFIX`
- `CELERY_BROKER_URL`, `CELERY_RESULT_BACKEND`
- `COMPARE_QUEUE_CPU`, `COMPARE_QUEUE_GPU`, `ENABLE_GPU_QUEUE`, `COMPARE_EXECUTION_DEVICE`
- `CELERY_CPU_CONCURRENCY`, `CELERY_GPU_CONCURRENCY` (w `tools/runtime/.env`)

Podczas startu aplikacji logowane są efektywne ustawienia runtime (API/jobs/logging). Wartości sekretów (np. `LOG_API_TOKEN`) nie są wypisywane wprost.

`/health` zwraca teraz dodatkowo pole `git` z: `branch`, `tag`, `last_commit`, `committer`, `date`.

Nadpisanie metadanych git przez env (opcjonalnie):
- `APP_GIT_BRANCH`
- `APP_GIT_TAG`
- `APP_GIT_LAST_COMMIT`
- `APP_GIT_COMMITTER`
- `APP_GIT_COMMIT_DATE`

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
- `requirements.prod.txt` – runtime (GPU, do produkcji)
- `requirements-dev.txt` – dev/test

---

## Dobre praktyki

- Nie pracujemy jako root
- Nie commitujemy .venv
- Używamy pre-commit
- Każdy commit powinien przechodzić make full-check

## Dokumentacja architektury

- Szczegóły hard-cut migration i architektury: `docs/architecture-celery-redis.md`
- Konfiguracja runtime compose: `tools/runtime/docker-compose.yml`
- Konfiguracja monitoringu compose: `tools/monitoring/docker-compose.yml`
