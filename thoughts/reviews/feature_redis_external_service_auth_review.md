## Validation Report: FEATURE-001 Redis External Service Auth/TLS Implementation Plan

### Implementation Status
✓ Phase 1: Redis Config Contract and Validation Core - Fully implemented
⚠️ Phase 2: Runtime Integration (JobStore, API Startup, Celery) - Implemented with minor deviations
✓ Phase 3: Documentation and Environment Wiring - Fully implemented

### Planned File Scope
Planned changes were present in these files:
- `app/core/config.py`
- `app/core/job_store.py`
- `app/main.py`
- `app/core/celery_app.py`
- `tests/test_config.py`
- `tests/test_api.py`
- `tests/test_job_store.py`
- `tools/runtime/.env.example`
- `config.toml.example`
- `tools/runtime/docker-compose.yml`
- `tools/monitoring/docker-compose.yml`
- `README.md`
- `README-DEV.md`
- `docs/architecture-celery-redis.md`

Planned but not materially changed:
- `tests/test_contracts.py`

### Automated Verification Results
✓ `pytest -q tests/test_config.py`
Result: 19 passed

✓ `ruff check app/core/config.py tests/test_config.py`
Result: passed

✓ `black --check app/core/config.py tests/test_config.py`
Result: passed with environment warning because Black is running under Python 3.10 while the project targets Python 3.12

✓ `pytest -q tests/test_job_store.py tests/test_api.py tests/test_contracts.py tests/test_config.py`
Result: 28 passed

✓ `ruff check app/core/job_store.py app/main.py app/core/celery_app.py tests`
Result: passed

✓ `black --check app/core/job_store.py app/main.py app/core/celery_app.py tests`
Result: passed with the same Python 3.10/3.12 warning

✓ `ruff check .`
Result: passed

✓ `black --check .`
Result: passed with the same Python 3.10/3.12 warning

✓ `pytest -q`
Result: 49 passed

Verification notes:
- All claimed automated checks passed in the current workspace.
- All pytest runs emit FastAPI deprecation warnings for `@app.on_event("startup")`.

### Code Review Findings

#### Matches Plan
- Centralized Redis settings and validation were added in `app/core/config.py:23-221`, including URL-first precedence, split vars fallback, TLS handling, and URL masking.
- JobStore now uses normalized Redis settings and adds explicit startup validation in `app/core/job_store.py:260-275` and `app/core/job_store.py:283-299`.
- API startup logs now use sanitized Redis fields in `app/main.py:21-38` and call startup validation in `app/main.py:63-86`.
- Celery now falls back to shared Redis settings when explicit broker/backend URLs are absent in `app/core/celery_app.py:18-20`.
- Tests were added for config precedence, invalid combinations, startup fail-fast behavior, and Celery fallback in `tests/test_config.py`, `tests/test_job_store.py`, and `tests/test_api.py`.
- Docs/examples were updated across `README.md`, `README-DEV.md`, `docs/architecture-celery-redis.md`, `tools/runtime/.env.example`, `config.toml.example`, and compose files.

#### Deviations from Plan
- `tests/test_contracts.py` was listed in Phase 2 but was not materially updated. Assessment: acceptable because the health response contract remained unchanged and existing coverage still passed.
- The plan described startup-time validation, but `create_app()` still instantiates the JobStore before the startup hook via `app/main.py:61` and `app/core/job_store.py:303`. Assessment: behavior is still fail-fast before serving requests, but invalid config or missing Redis package can fail during app construction rather than strictly inside startup.

#### Potential Issues
- No live integration test proves a real authenticated `rediss://` connection works end-to-end. Current coverage relies on mocked Redis behavior in `tests/test_api.py:60-106` and config-level URL assertions in `tests/test_config.py:157-181`.
- FastAPI startup handling uses deprecated `@app.on_event("startup")` in `app/main.py:63`, which caused warnings in every pytest run. This is not a functional bug today, but it is maintenance debt.

### Manual Testing Required
1. URL mode:
- [ ] Set `JOB_STORE_BACKEND=redis`
- [ ] Set `REDIS_URL=rediss://user:pass@host:port/0`
- [ ] Start the API and confirm startup succeeds
- [ ] Call `/health` and confirm `job_store.available` is `true`

2. Split-vars mode:
- [ ] Clear `REDIS_URL`
- [ ] Set `REDIS_HOST`, `REDIS_PORT`, `REDIS_DB`, `REDIS_USERNAME`, `REDIS_PASSWORD`, `REDIS_TLS=true`
- [ ] Start the API and confirm startup succeeds
- [ ] Submit a compare job and poll until completion

3. Failure behavior:
- [ ] Set invalid Redis credentials
- [ ] Start the API and confirm it exits before serving requests
- [ ] Confirm logs mention the invalid setting or startup ping failure without exposing the password

4. Local compose compatibility:
- [ ] Start `docker compose -f tools/runtime/docker-compose.yml --profile cpu up --build`
- [ ] Confirm local default Redis mode still runs without additional required secrets

### Recommendations
- Add one integration test path against a real auth-enabled Redis instance, ideally covering `rediss://` as well as split-vars mode.
- Consider moving JobStore creation into a FastAPI lifespan/startup path if the team wants all Redis contract failures to occur strictly during application startup.
- Replace `@app.on_event("startup")` with lifespan handlers to remove the current deprecation warnings.
