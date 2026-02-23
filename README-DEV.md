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

Walidacja job settings:
- COMPARE_JOB_WORKERS: zakres 1..(CPU_COUNT * 4)
- QUEUE_MAXSIZE: minimum 0

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
