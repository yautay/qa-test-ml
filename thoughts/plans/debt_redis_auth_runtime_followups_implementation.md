# DEBT-001 Redis Auth Runtime Follow-ups Implementation Plan

## Overview

Close the Redis auth runtime follow-ups left after the original feature rollout by moving API-side Redis `JobStore` initialization into FastAPI lifespan/startup, replacing deprecated startup hooks, adding local real-Redis auth integration coverage, and documenting how to run and verify those scenarios.

## Current State Analysis

The repo already supports shared Redis configuration through `REDIS_URL` or split vars, startup ping validation, and sanitized Redis logging, but the lifecycle boundary is still wrong for this ticket and the integration coverage is still incomplete.

- `create_app()` still eagerly creates the store via `app.state.job_store = get_job_store()` in `app/main.py:60-61`, so Redis config/package/client creation failures can happen during app construction rather than strictly in startup.
- API startup still uses deprecated `@app.on_event("startup")` in `app/main.py:63`.
- `/health` currently reads `request.app.state.job_store` defensively and reports `job_store.available` separately from top-level status in `app/api/routes/health.py:42-58`.
- Compare routes already tolerate missing startup initialization by returning `503` if no store is present in `app/api/routes/compare.py:191-196`.
- Real Redis auth coverage is missing; existing startup tests only use fake Redis clients in `tests/test_api.py:60-106`, and current Redis tests are unit-level fakes in `tests/test_job_store.py:10-98`.
- There is no dedicated integration marker today; `pytest.ini:1-6` contains no marker registration.
- One repo-specific constraint must be accounted for in the plan: `compare_router` imports `celery_app`, and `celery_app` is instantiated at import in `app/core/celery_app.py:45`, so shared Redis config may still be resolved too early unless that path is kept explicit or minimally deferred.

## Desired End State

After this work:

- API-side Redis `JobStore` creation and fail-fast validation happen in FastAPI lifespan/startup rather than during `create_app()`.
- Standard API startup no longer uses deprecated `@app.on_event(...)` and no longer emits the FastAPI deprecation warning in the affected default test path.
- The repo contains a dedicated local-only integration suite for auth-enabled Redis covering:
  - `REDIS_URL` mode
  - split-vars mode
  - negative bad-credentials fail-fast behavior
- The integration suite uses a separate pytest marker/category so it does not run under plain `pytest -q`.
- The documented local workflow explains how to bring up an auth-enabled Redis instance, run the tests, and verify the expected behavior.

Verification target:

- `create_app()` can be constructed without touching Redis store initialization for the API path.
- Entering the app lifespan triggers store creation and startup validation.
- `/health` remains controlled and explicit about job-store availability.
- Real Redis auth integration tests pass locally in both supported config modes.

### Key Discoveries:
- The current startup logic already separates store validation from route behavior, so moving creation into lifespan is a small change in `app/main.py` rather than a broad route refactor (`app/main.py:60-86`, `app/api/routes/compare.py:191-196`, `app/api/routes/health.py:42-58`).
- Existing route code already supports a startup-managed store because both `/health` and compare handlers guard against a missing `app.state.job_store` (`app/api/routes/health.py:43-49`, `app/api/routes/compare.py:192-196`).
- The best existing test lifecycle pattern is the context-managed `TestClient` fixture in `tests/test_jobs_api.py:34-48`; new lifespan-sensitive tests should follow that pattern.
- The shared Redis config contract is already centralized in `app/core/config.py:23-221`, so the integration work should reuse it rather than adding test-only config branches.
- Celery currently falls back to shared Redis settings at app creation time through `create_celery_app()` in `app/core/celery_app.py:18-20`, and the module-level `celery_app = create_celery_app()` at `app/core/celery_app.py:45` is the only remaining path that can still resolve shared Redis before API lifespan.

## What We're NOT Doing

- No TLS or `rediss://` feature expansion beyond the already-supported config contract.
- No CI wiring for the new integration tests.
- No redesign of compare job semantics, Celery task routing, or Redis data model.
- No broad dependency-injection rewrite for the app or worker runtime.
- No large `/health` contract redesign beyond a minimal controlled adjustment if needed to support lifespan-based initialization.
- No broader cleanup of unrelated startup patterns outside the direct Redis/API flow; additional findings should be documented as follow-up work.

## Implementation Approach

Use the smallest repo-aligned change set:

1. Replace the deprecated startup hook in `app/main.py` with a FastAPI lifespan context manager.
2. Move API-side `JobStore` creation and Redis startup validation into that lifespan path, while preserving route behavior and `/health` semantics.
3. Keep the current global `get_job_store()` cache unless the minimal Celery import-time adjustment requires a small helper split between creation and retrieval.
4. Add a dedicated integration marker and a real-Redis auth integration test suite that uses authenticated Redis plus eager Celery execution to cover startup, `/health`, job creation, and persisted job reads without requiring a separate live worker.
5. Document the local setup and commands in developer-facing docs, and register the marker in pytest config.

## Phase 1: Lifecycle Migration

### Overview
Move API-side store creation into FastAPI lifespan/startup, remove deprecated startup hooks, and include the minimal Celery import-time fix only if it stays directly tied to this lifecycle correction.

### Changes Required:

#### 1. FastAPI app lifecycle
**File**: `app/main.py`
**Changes**:
- Replace `@app.on_event("startup")` with a lifespan context manager.
- Stop assigning `app.state.job_store = get_job_store()` during `create_app()`.
- In lifespan startup:
  - read runtime settings
  - create the `JobStore`
  - assign it to `app.state.job_store`
  - run `validate_redis_job_store_startup(...)`
  - emit the existing sanitized startup log payload
- In lifespan shutdown:
  - keep cleanup minimal; if no explicit store teardown is needed, just ensure state remains well-defined.
- If useful for route clarity, initialize `app.state.job_store = None` before lifespan starts so route guards remain explicit.

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    job_store_backend = _read_runtime_settings()
    store = get_job_store()
    app.state.job_store = store
    validate_redis_job_store_startup(store)
    logger.info("Application startup settings: {}", settings)
    yield
```

#### 2. Job store access and cache behavior
**File**: `app/core/job_store.py`
**Changes**:
- Keep the current `create_job_store()` / `get_job_store()` split if it remains sufficient.
- If lifecycle migration or Celery import-order work requires it, introduce only the smallest helper necessary to avoid forcing API store creation too early while preserving worker-side retrieval.
- Preserve existing memory/redis backend behavior and startup validation semantics.

#### 3. Minimal Celery import-time alignment
**File**: `app/core/celery_app.py`
**Changes**:
- Review whether shared Redis config resolution at module import still creates an API-startup timing conflict after the lifespan migration.
- If the conflict remains and the fix is small, minimally defer or isolate shared Redis fallback so API import does not reintroduce premature Redis contract failures through `celery_app` import alone.
- Preserve current precedence rules:
  - `CELERY_BROKER_URL` overrides shared Redis
  - `CELERY_RESULT_BACKEND` overrides broker/shared backend behavior

#### 4. Contract-preserving route behavior
**Files**:
- `app/api/routes/health.py`
- `app/api/routes/compare.py`
**Changes**:
- Keep current defensive handling of missing `job_store` unless a minimal clarification is needed.
- Preserve the controlled `/health` contract shape unless a small semantic cleanup is required by lifespan timing.
- Preserve compare endpoint behavior that returns `503` when the store is unavailable.

#### 5. Lifecycle-sensitive test updates
**Files**:
- `tests/test_api.py`
- `tests/test_config.py`
- `tests/test_contracts.py`
- `tests/test_jobs_api.py`
**Changes**:
- Update tests that currently expect `app.state.job_store` to exist immediately after `create_app()`.
- Standardize lifespan-sensitive tests around context-managed `TestClient(...)` usage, following `tests/test_jobs_api.py:34-48`.
- Add assertions that the Redis startup failure now occurs when entering app lifespan rather than while constructing the app object.
- Confirm the deprecation-warning path is removed from the default covered test set.

### Success Criteria:

#### Automated Verification:
- [x] Lifecycle tests pass for API startup behavior: `pytest -q tests/test_api.py tests/test_config.py tests/test_contracts.py tests/test_jobs_api.py`
- [x] No FastAPI deprecation warning remains from `@app.on_event(...)` in the affected default test path.
- [x] Lint passes for lifecycle/runtime files: `ruff check app/main.py app/core/job_store.py app/core/celery_app.py tests`
- [x] Formatting passes for lifecycle/runtime files: `black --check app/main.py app/core/job_store.py app/core/celery_app.py tests`

#### Manual Verification:
- [ ] Starting the API with valid Redis config succeeds after entering lifespan, not during plain app construction.
- [ ] With invalid Redis credentials, the API does not begin serving requests.
- [ ] `/health` still returns the expected response shape and controlled job-store availability signal.
- [ ] Compare endpoints still return controlled `503` behavior if startup-managed store state is absent.

---

## Phase 2: Integration Test Coverage

### Overview
Add local real-Redis auth integration tests for URL mode, split-vars mode, and bad-credentials fail-fast behavior, using eager Celery to keep the suite local and deterministic.

### Changes Required:

#### 1. Integration marker and test segregation
**Files**:
- `pytest.ini`
- `tests/` test modules for new integration coverage
**Changes**:
- Register a dedicated marker such as `redis_integration` or equivalent in `pytest.ini`.
- Ensure the new tests are excluded from plain `pytest -q` by running only when explicitly selected with `-m` or by file path.
- Keep the marker naming explicit to this dependency and avoid conflating it with unit tests.

#### 2. Real Redis auth integration suite
**File**: `tests/test_redis_auth_integration.py`
**Changes**:
- Add a new integration test module dedicated to this ticket’s live Redis auth scenarios.
- Use an authenticated local Redis instance and eager Celery execution (`CELERY_TASK_ALWAYS_EAGER=true`) to cover the full flow without a separate worker process.
- Cover these scenarios:
  - `REDIS_URL` auth mode
  - split-vars auth mode
  - bad credentials fail-fast path
- Positive scenarios should verify:
  - app startup succeeds
  - `/health` reports `job_store.backend == "redis"` and `job_store.available is True`
  - job creation succeeds through `POST /v1/compare/jobs`
  - persisted job status can be read back through `GET /v1/compare/jobs/{id}`
- Negative scenario should verify:
  - app startup fails fast when credentials are rejected
  - surfaced exception/log assertions do not contain the configured raw password literal

```python
@pytest.mark.redis_integration
def test_redis_auth_url_mode_full_flow(...):
    with TestClient(create_app()) as client:
        assert client.get("/health").json()["job_store"] == {"backend": "redis", "available": True}
        ...
```

#### 3. Shared test fixtures for live auth Redis
**Files**:
- `tests/conftest.py` or the new integration test module
- optionally a dedicated helper module under `tests/`
**Changes**:
- Add only the minimum fixture support needed to:
  - set auth-enabled Redis env vars
  - clear config/store caches between scenarios
  - ensure eager Celery mode is enabled for the integration flow
  - skip cleanly when the local Redis auth dependency is not available or not explicitly requested
- Keep fixture behavior isolated so default unit/API tests remain fast and independent.

#### 4. Logging and secret-leak assertions
**Files**:
- `tests/test_api.py`
- `tests/test_config.py`
- `tests/test_redis_auth_integration.py`
**Changes**:
- Add targeted assertions that failure messages and captured logs do not expose `REDIS_PASSWORD` literals.
- Reuse existing masking expectations from `tests/test_config.py:147-155` rather than creating a second masking convention.

### Success Criteria:

#### Automated Verification:
- [ ] URL-mode live auth integration passes: `pytest -q -m redis_integration tests/test_redis_auth_integration.py -k url`
- [ ] Split-vars live auth integration passes: `pytest -q -m redis_integration tests/test_redis_auth_integration.py -k split`
- [ ] Bad-credentials fail-fast integration passes: `pytest -q -m redis_integration tests/test_redis_auth_integration.py -k invalid`
- [x] Default test run remains cleanly separated from the integration suite: `pytest -q`
- [x] Lint passes for new integration tests: `ruff check tests`
- [x] Formatting passes for new integration tests: `black --check tests`

#### Manual Verification:
- [ ] A developer can start an auth-enabled Redis locally and run the integration suite without a separate Celery worker.
- [ ] Both supported config modes exercise the same real Redis instance successfully.
- [ ] The negative credential scenario fails before the app begins serving traffic.
- [ ] Error output and logs do not reveal the configured password.

---

## Phase 3: Documentation And Test Entry Points

### Overview
Document the local workflow for auth-enabled Redis integration testing and surface the new test entry points without changing the default developer path.

### Changes Required:

#### 1. Dedicated integration-test documentation
**File**: `docs/testing-integration.md`
**Changes**:
- Add a focused guide for local integration tests that need external services.
- Document the auth-enabled Redis setup expected by the new suite.
- Include both supported local approaches allowed by the ticket:
  - `docker compose`
  - another repeatable local mechanism, if the implementation chooses one
- Document explicit commands for:
  - preparing env
  - starting Redis with auth
  - running the integration marker/file
  - tearing the environment down

#### 2. Developer-facing quick links
**Files**:
- `README-DEV.md`
- `README.md`
**Changes**:
- Keep the default `pytest -q` workflow intact.
- Add a short section or link pointing to the dedicated integration-test guide.
- Clarify that the live Redis auth tests are opt-in and intentionally separate from the default suite.

#### 3. Runtime examples and compose notes
**Files**:
- `tools/runtime/.env.example`
- `tools/runtime/docker-compose.yml`
**Changes**:
- Add or refine examples for auth-enabled local Redis usage relevant to the integration suite.
- If a dedicated compose override or auth-enabled Redis service is needed for local testing, document it with the smallest possible addition.
- Preserve existing local default compose compatibility for developers who are not running the auth integration flow.

#### 4. Optional architecture note update
**File**: `docs/architecture-celery-redis.md`
**Changes**:
- Update the lifecycle/startup wording if needed so the architecture doc matches the new lifespan-based initialization behavior.
- Keep this update minimal and factual.

### Success Criteria:

#### Automated Verification:
- [x] Documentation references the new integration path consistently across the updated docs.
- [x] `ruff check .`
- [x] `black --check .`

#### Manual Verification:
- [ ] A developer can follow the docs to run the auth-enabled Redis integration suite locally.
- [ ] The docs make it clear that `pytest -q` remains the default path and does not include the live Redis suite.
- [ ] The documented local Redis auth setup matches the actual test expectations.
- [ ] Existing local compose usage remains understandable and backward-compatible for non-auth testing.

---

## Testing Strategy

### Unit Tests:
- Lifespan migration should keep unit-level coverage for config parsing and startup validation intact.
- Add focused assertions for any new helper introduced to support deferred store creation or minimal Celery fallback changes.
- Preserve current coverage for Redis masking and startup validation semantics in `tests/test_config.py` and `tests/test_job_store.py`.

### Integration Tests:
- Real Redis auth with `REDIS_URL` plus eager Celery full flow.
- Real Redis auth with split vars plus eager Celery full flow.
- Real Redis auth negative credentials path that fails before serving requests.
- Integration test selection through a dedicated pytest marker so the suite stays opt-in.

### Manual Testing Steps:
1. Start a local auth-enabled Redis instance using the documented setup.
2. Run the URL-mode integration path and confirm startup, `/health`, job creation, and job readback all succeed.
3. Run the split-vars integration path and confirm the same flow succeeds.
4. Re-run with incorrect credentials and confirm startup fails before serving requests.
5. Inspect the error output/logs and confirm the configured password does not appear.

## Performance Considerations

- Lifespan-based initialization changes startup timing but not steady-state request or task behavior.
- The Redis startup ping remains a one-time startup cost for API initialization.
- The new live integration suite should remain opt-in so it does not slow the default developer test loop.

## Migration Notes

- Existing users of `REDIS_URL` and split-vars config remain compatible; the primary change is when API-side initialization occurs.
- Tests that currently inspect `app.state.job_store` immediately after `create_app()` must be updated to enter lifespan first.
- If the minimal Celery import-time adjustment is needed, it must preserve current explicit override behavior for `CELERY_BROKER_URL` and `CELERY_RESULT_BACKEND`.

## References

- Original ticket: `thoughts/tickets/debt_redis_auth_runtime_followups.md`
- Related review: `thoughts/reviews/feature_redis_external_service_auth_review.md`
- Prior implementation plan: `thoughts/plans/feature_redis_external_service_auth_implementation.md`
- Current eager store creation: `app/main.py:60-61`
- Deprecated startup hook: `app/main.py:63`
- Current startup validation/logging block: `app/main.py:64-86`
- `/health` job-store contract: `app/api/routes/health.py:42-58`
- Compare-route missing-store handling: `app/api/routes/compare.py:191-196`
- Shared Redis config contract: `app/core/config.py:23-221`
- JobStore factory/cache: `app/core/job_store.py:273-304`
- Celery shared Redis fallback and import-time app creation: `app/core/celery_app.py:18-20`, `app/core/celery_app.py:45`
- Current mocked startup tests: `tests/test_api.py:60-106`
- Existing context-managed TestClient pattern: `tests/test_jobs_api.py:34-48`
- Current pytest config: `pytest.ini:1-6`
