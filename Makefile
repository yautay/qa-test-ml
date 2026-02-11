.PHONY: help install install-dev test lint format type audit deps freeze clean full-check

help:
	@echo "Dostępne komendy:"
	@echo "  make install        - instalacja runtime"
	@echo "  make install-dev    - instalacja dev"
	@echo "  make test           - uruchom testy"
	@echo "  make lint           - uruchom ruff"
	@echo "  make format         - formatowanie black"
	@echo "  make type           - mypy"
	@echo "  make audit          - pip-audit"
	@echo "  make deps           - pipdeptree"
	@echo "  make freeze         - zapis locka"
	@echo "  make full-check     - pełny check przed commitem"
	@echo "  make clean          - usuń cache"

install:
	pip install -r requirements.txt

install-dev:
	pip install -r requirements-dev.txt

test:
	pytest -q

lint:
	ruff check .

format:
	black .

type:
	mypy .

audit:
	pip-audit

deps:
	pipdeptree

freeze:
	pip freeze > requirements.lock.txt

full-check:
	pytest -q && ruff check . && mypy . && pip-audit && pre-commit run --all-files

clean:
	find . -type d -name "__pycache__" -exec rm -r {} +
	find . -type d -name ".pytest_cache" -exec rm -r {} +
	find . -type d -name ".mypy_cache" -exec rm -r {} +

precommit:
	pre-commit run --all-files
