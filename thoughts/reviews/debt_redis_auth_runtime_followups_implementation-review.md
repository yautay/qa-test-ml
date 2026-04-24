# Validation Report: debt_redis_auth_runtime_followups_implementation.md

## Scope Reviewed

- Plan: `thoughts/plans/debt_redis_auth_runtime_followups_implementation.md`
- Ticket: `thoughts/tickets/debt_redis_auth_runtime_followups.md`
- Implementation window reviewed: commits `768bf9f`, `3a1da67`, `2348c59` (plus current branch state)

## Context Discovery

### Planned change targets identified

- Phase 1 (lifecycle/runtime):
  - `app/main.py`
  - `app/core/job_store.py`
  - `app/core/celery_app.py`
  - `app/api/routes/health.py`
  - `app/api/routes/compare.py`
  - `tests/test_api.py`
  - `tests/test_config.py`
  - `tests/test_contracts.py`
  - `tests/test_jobs_api.py`
- Phase 2 (integration coverage):
  - `pytest.ini`
  - `tests/test_redis_auth_integration.py`
  - `tests/conftest.py` (optional) or helper fixtures in integration module
  - `tests/test_api.py`
  - `tests/test_config.py`
- Phase 3 (docs and entry points):
  - `docs/testing-integration.md`
  - `README-DEV.md`
  - `README.md`
  - `tools/runtime/.env.example`
  - `tools/runtime/docker-compose.yml`
  - `docs/architecture-celery-redis.md` (optional)

### Key functionality expected

- `create_app()` must not initialize Redis `JobStore` eagerly.
- Redis startup validation must happen on entering FastAPI lifespan.
- Deprecated `@app.on_event("startup")` path should be removed.
- Integration tests should cover URL mode, split-vars mode, and invalid credentials.
- Integration suite should remain opt-in and documented.

## Implementation Status

- ✓ Phase 1: Lifecycle Migration - fully implemented
- ✓ Phase 2: Integration Test Coverage - implemented
- ✓ Phase 3: Documentation and Test Entry Points - fully implemented

## Phase-by-Phase Validation

### Phase 1: Lifecycle Migration

Matches plan:

- `app/main.py` now uses FastAPI lifespan (`asynccontextmanager`) and no longer uses `@app.on_event(...)`.
- `create_app()` initializes `app.state.job_store = None`; actual store creation moved into lifespan startup (`get_job_store()` + `validate_redis_job_store_startup(...)`).
- Startup logging uses sanitized Redis details via `get_redis_connection_settings()` and `mask_redis_url(...)`.
- Lifespan shutdown resets `app.state.job_store = None`.
- `app/core/celery_app.py` was adjusted with lazy wrapper (`_LazyCeleryApp`) to avoid import-time eager Redis config resolution and to preserve explicit broker/backend precedence.
- Route contracts remained defensive:
  - `/health` still reports controlled `job_store.backend` + `available`.
  - Compare route still returns controlled `503` when store is missing.
- Lifecycle-sensitive tests updated:
  - `tests/test_api.py`, `tests/test_config.py`, `tests/test_contracts.py` now exercise lifespan with context-managed `TestClient`.
  - Added assertion coverage that `create_app()` defers store initialization until lifespan.

Notes:

- `tests/test_jobs_api.py` was listed in plan but did not require direct change for lifecycle migration because existing usage already relied on context-managed `TestClient`.

### Phase 2: Integration Test Coverage

Matches plan:

- Marker registered: `redis_integration` in `pytest.ini`.
- New suite added: `tests/test_redis_auth_integration.py`.
- Scenarios implemented:
  - URL mode full flow (`test_redis_auth_url_mode_full_flow`)
  - Split-vars full flow (`test_redis_auth_split_vars_mode_full_flow`)
  - Invalid credentials fail-fast + secret leak checks (`test_redis_auth_invalid_credentials_fail_fast_without_secret_leak`)
- Fixture behavior includes:
  - explicit opt-in gate (`RUN_REDIS_INTEGRATION`)
  - live Redis availability check
  - eager Celery flags
  - runtime cache clearing including Celery app cache

Note:

- Follow-up adjustment applied: default pytest selection now excludes `redis_integration` tests via `addopts = -m "not redis_integration"` in `pytest.ini`.

### Phase 3: Documentation and Test Entry Points

Matches plan:

- Added dedicated guide: `docs/testing-integration.md`.
- Updated `README.md` and `README-DEV.md` with explicit opt-in guidance and links.
- Updated runtime examples:
  - `tools/runtime/.env.example` includes auth integration helper vars.
  - `tools/runtime/docker-compose.yml` includes `redis-auth` service/profile.
- Architecture note updated in `docs/architecture-celery-redis.md` to reflect lifespan-based startup.

## Automated Verification Results

- ✓ `pytest -q tests/test_api.py tests/test_config.py tests/test_contracts.py tests/test_jobs_api.py`
  - Result: `42 passed`
- ✓ No FastAPI `@app.on_event(...)` deprecation path observed in default covered tests
  - Confirmed via code search and test output
- ✓ `ruff check app/main.py app/core/job_store.py app/core/celery_app.py tests`
- ✓ `black --check app/main.py app/core/job_store.py app/core/celery_app.py tests`
  - Command succeeded with environment warning about Black parser Python version

- ⚠️ `pytest -q -m redis_integration tests/test_redis_auth_integration.py -k url`
  - Result: `1 skipped, 2 deselected` (not executed live)
- ⚠️ `pytest -q -m redis_integration tests/test_redis_auth_integration.py -k split`
  - Result: `1 skipped, 2 deselected` (not executed live)
- ⚠️ `pytest -q -m redis_integration tests/test_redis_auth_integration.py -k invalid`
  - Result: `1 skipped, 2 deselected` (not executed live)

- ✓ `pytest -q`
  - Result: `50 passed, 3 deselected`
- ✓ `ruff check tests`
- ✓ `black --check tests`
  - Command succeeded with environment warning about Black parser Python version

- ✓ `ruff check .`
- ✓ `black --check .`
  - Command succeeded with environment warning about Black parser Python version

## Code Review Findings

### Matches Plan

- Lifecycle boundary moved from app construction to startup/lifespan.
- Deprecated FastAPI startup hook removed.
- Minimal Celery import-time alignment implemented via lazy app wrapper.
- Integration test suite and marker are present and aligned to required scenarios.
- Documentation for local auth Redis flow is present and coherent.

### Deviations from Plan

- No explicit `## Deviations from Plan` section exists in the implementation plan.
- Additional deviation found: none (selection behavior previously flagged has been corrected via pytest `addopts`).

### Potential Issues / Edge Cases

- Live integration criteria are not truly validated in this review environment because tests skipped without `RUN_REDIS_INTEGRATION=1` and reachable auth Redis.
- Integration tests still rely on explicit env gating (`RUN_REDIS_INTEGRATION`) and live Redis availability; marker selection alone can still skip execution if env is missing.
- Black checks emit recurring interpreter-version warning (non-blocking now, but can confuse CI/local verification output).

## Manual Testing Required

1. Live Redis auth execution:
   - [ ] Start auth Redis (`docker compose -f tools/runtime/docker-compose.yml --profile redis-auth up -d redis-auth`)
   - [ ] Export `RUN_REDIS_INTEGRATION=1`
   - [ ] Export `PMS_REDIS_AUTH_URL='redis://:pms-secret@127.0.0.1:6380/0'`
2. Run each scenario and confirm real execution (not skip):
   - [ ] `pytest -q -m redis_integration tests/test_redis_auth_integration.py -k url`
   - [ ] `pytest -q -m redis_integration tests/test_redis_auth_integration.py -k split`
   - [ ] `pytest -q -m redis_integration tests/test_redis_auth_integration.py -k invalid`
3. Runtime behavior checks:
   - [ ] Confirm app serves only after lifespan startup with valid credentials
   - [ ] Confirm invalid credentials fail before serving requests
   - [ ] Confirm `/health` response shape and `job_store` fields remain stable
   - [ ] Confirm no raw Redis password appears in error output/logs

## Recommendations

- Keep current implementation; it is largely aligned and passes all non-live automated checks.
- For full closure of Phase 2 success criteria, run live auth integration commands in an environment with Redis auth enabled and attach results.
