# AGENTS

## Fast Facts
- Python `3.12`.
- Main app entrypoint: `app.main:create_app`; runtime serves `/health`, `/metrics`, and `/v1/compare/*`.
- The async flow is: FastAPI route -> `JobStore` -> Celery task -> metric registry -> shared job state back in store.

## High-Value Commands
- Install runtime deps: `pip install -r requirements.txt`
- Install dev deps: `pip install -r requirements-dev.txt`
- Run app locally: `uvicorn app.main:app --reload`
- Fast test pass: `pytest -q`
- Single test/file: `pytest -q tests/test_jobs_api.py -k <expr>`
- Lint: `ruff check .`
- Format check: `black --check .`
- Type check: `mypy .`
- CI-equivalent security checks: `pip-audit` and `bandit -r app/ -ll`
- Convenience sweep: `make full-check`

## Verified Workflow Notes
- CI installs `requirements-dev.txt` and then runs: tests with coverage -> `ruff check .` -> `black --check .` -> `mypy .` -> `pip-audit` -> `bandit -r app/ -ll`.
- `make full-check` is not identical to CI: it skips `black --check` and instead ends with `pre-commit run --all-files`.
- Pre-commit runs `ruff --fix`, `black`, and `mypy`; expect hooks to rewrite files.

## Architecture Boundaries
- Keep HTTP concerns in `app/api/routes/*`; shared runtime/config/infrastructure lives in `app/core/*`.
- Metric implementations live in `app/metrics/*` and must be registered in `app/core/registry.py` or the app will not expose/use them.
- Celery is configured in `app/core/celery_app.py`; compare jobs are executed by `app.tasks.compare_tasks.process_compare_job`.

## Config And Runtime Gotchas
- Config resolution order is cached and is: process env -> `config.toml` `[env]` -> code defaults.
- If tests change env vars, clear config/store caches like the existing tests do (`app.core.config._clear_config_cache()`, `app.core.job_store._clear_job_store_cache()`, and HMAC nonce cache when relevant).
- `JOB_STORE_BACKEND=redis` is fail-fast at app startup. Most tests use `JOB_STORE_BACKEND=memory`.
- For API/job tests, set `CELERY_TASK_ALWAYS_EAGER=true`; existing tests also set `CELERY_TASK_EAGER_PROPAGATES=false`.
- `COMPARE_TMP_DIR` must stay inside `IMAGE_BASE_DIR`; the repo's safe default is `IMAGE_BASE_DIR=.` with `COMPARE_TMP_DIR=.compare_tmp`.
- GPU routing is not controlled by `COMPARE_EXECUTION_DEVICE` alone; `ENABLE_GPU_QUEUE=true` must also be set or jobs stay on the CPU queue.
- GPU task failures can requeue once onto the CPU queue; preserve that behavior when touching task error handling.
- Keep `PROMETHEUS_MULTIPROC_DIR` outside the repo (for example `/tmp/pms-prom-worker`) or worker `*.db` shards will pollute `git status`.

## Docker And Integration Tests
- Runtime compose file: `tools/runtime/docker-compose.yml`; copy `tools/runtime/.env.example` to `tools/runtime/.env` before using it.
- Compose profiles are meaningful: `cpu`, `gpu`, and `redis-auth`.
- Local auth-enabled Redis for tests: `docker compose -f tools/runtime/docker-compose.yml --profile redis-auth up -d redis-auth`
- Redis auth integration suite is opt-in only: `RUN_REDIS_INTEGRATION=1 PMS_REDIS_AUTH_URL='redis://:pms-secret@127.0.0.1:6380/0' pytest -q -m redis_integration tests/test_redis_auth_integration.py`
- Worker containers download model checkpoints on startup (`alexnet` and `vgg16`), so first boot needs network and is slower than a normal Python service.
