.PHONY: help install install-dev test lint format type audit deps freeze clean full-check coverage coverage-report

help:
	@echo "Available commands:"
	@echo "  make install           - install runtime dependencies"
	@echo "  make install-dev       - install dev dependencies"
	@echo "  make test              - run tests"
	@echo "  make lint              - run ruff"
	@echo "  make format            - format with black"
	@echo "  make type              - run mypy"
	@echo "  make audit             - run pip-audit"
	@echo "  make deps              - run pipdeptree"
	@echo "  make freeze            - save lock file"
	@echo "  make full-check        - full check before commit"
	@echo "  make coverage          - run tests with coverage"
	@echo "  make coverage-report   - generate HTML coverage report"
	@echo "  make clean             - remove cache"

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

coverage:
	pytest --cov=app --cov-report=term-missing

coverage-report:
	pytest --cov=app --cov-report=html && python -m http.server 8000 --directory htmlcov

clean:
	find . -type d -name "__pycache__" -exec rm -r {} +
	find . -type d -name ".pytest_cache" -exec rm -r {} +
	find . -type d -name ".mypy_cache" -exec rm -r {} +

precommit:
	pre-commit run --all-files
