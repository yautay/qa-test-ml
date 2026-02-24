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

Opcjonalnie konfiguracja przez plik:

cp config.toml.example config.toml

Priorytet ustawień: zmienne systemowe > config.toml > domyślne wartości w kodzie.

Jak ustawiać zmienne:

- Systemowo (najwyższy priorytet), np. `export LOG_LEVEL=DEBUG`
- W `config.toml` w sekcji `[env]`, np. `LOG_LEVEL = "DEBUG"`
- Jeżeli nie ustawisz żadnej z powyższych, aplikacja bierze wartość domyślną z kodu

Walidacja job settings:
- COMPARE_JOB_WORKERS: zakres 1..(CPU_COUNT * 4)
- QUEUE_MAXSIZE: minimum 0

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

- requirements.txt – runtime
- requirements-dev.txt – dev/test
- requirements.lock.txt – pełny lock (opcjonalnie)

---

## Dobre praktyki

- Nie pracujemy jako root
- Nie commitujemy .venv
- Używamy pre-commit
- Każdy commit powinien przechodzić make full-check
