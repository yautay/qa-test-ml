# FEATURE-001 Redis External Service Auth/TLS Implementation Plan

## Overview

Implement configurable connection to an external Redis service for PMS using either `REDIS_URL` or split environment variables, with username/password auth, `rediss://` TLS support, startup fail-fast validation, secret-safe logging, and updated docs/examples. The change must preserve existing PMS queue/job semantics.

## Current State Analysis

Redis configuration is currently URL-only in core runtime paths, with no explicit URL/auth/TLS validation and no startup connectivity fail-fast for Redis.

- `app/core/job_store.py:266` reads only `REDIS_URL` with a local default.
- `app/core/job_store.py:276` creates client via `Redis.from_url(...)` directly.
- `app/core/celery_app.py:19` and `app/core/celery_app.py:20` use URL fallback chain for broker/backend only.
- `app/main.py:41` initializes job store, but `app/main.py:43` startup hook does not fail startup on Redis reachability.
- `app/core/job_store.py:251` ping exists only in `is_available()` used by health endpoint at `app/api/routes/health.py:48`.
- `app/main.py:49` logs raw `redis_url` in startup settings, which can leak URL-embedded credentials.

## Desired End State

PMS supports two Redis configuration modes with URL-first precedence:

1. `REDIS_URL` (including optional embedded auth + `redis://` / `rediss://`)
2. Split vars fallback (no URL present): `REDIS_HOST`, `REDIS_PORT`, `REDIS_DB`, `REDIS_USERNAME`, `REDIS_PASSWORD`, `REDIS_TLS`

Startup behavior for API process:
- validates Redis config contract (including TLS/auth combinations)
- creates JobStore client
- performs fail-fast ping against JobStore Redis
- aborts startup with a clear `RuntimeError` if validation/connectivity fails

Runtime behavior:
- existing queue/job semantics remain unchanged
- Redis operational issues continue to be logged through existing logger patterns
- logs and startup settings do not expose raw credentials

### Key Discoveries:
- Config precedence pattern already exists and should be reused (`env > config.toml > defaults`) in `app/core/config.py:56`.
- Fail-fast style for invalid security config already exists in `app/core/hmac_auth.py:24` and test style in `tests/test_config.py:129`.
- Health check currently relies on boolean availability via ping in `app/core/job_store.py:251`, so startup fail-fast needs a non-silent validation path.
- Docs/examples currently advertise only URL-based Redis setup in `tools/runtime/.env.example:19` and `config.toml.example:21`.

## What We're NOT Doing

- No refactor of compare job lifecycle, task routing, or result semantics.
- No change to Celery retry semantics beyond using new Redis config values.
- No dynamic secret rotation without restart.
- No advanced TLS client cert management (ticket scope is `rediss://` only).
- No fallback to an alternate Redis instance when primary config fails.

## Implementation Approach

Create a centralized Redis configuration resolver/validator in core config utilities, then consume it from JobStore and Celery URL resolution paths. Keep existing defaults and precedence behavior. Add startup fail-fast ping in API lifecycle. Replace potentially sensitive startup log fields with sanitized forms (`*_configured`, masked URLs/hosts). Finally, update tests/docs/examples to enforce and document the contract.

## Phase 1: Redis Config Contract and Validation Core

### Overview
Introduce a single source of truth for Redis connection settings and validation rules.

### Changes Required:

#### 1. Core config helpers
**File**: `app/core/config.py`
**Changes**:
- Add typed helper(s) to resolve Redis config with URL-first precedence.
- Parse split vars:
  - `REDIS_HOST` (default `127.0.0.1`)
  - `REDIS_PORT` (default `6379`)
  - `REDIS_DB` (default `0`)
  - `REDIS_USERNAME` (optional)
  - `REDIS_PASSWORD` (optional)
  - `REDIS_TLS` (bool, default `false`)
- Provide utility to build normalized Redis URL from split vars.
- Validate scheme/contract:
  - URL scheme must be `redis` or `rediss`.
  - If split `REDIS_TLS=true`, generated URL uses `rediss://`.
  - Empty/blank required split elements produce clear `RuntimeError` messages.
- Add masking helper for logging (`redis://user:***@host:port/db` style) and/or boolean configured flags.

```python
@dataclass(frozen=True)
class RedisConnectionSettings:
    url: str
    source: Literal["redis_url", "split_vars"]
    tls_enabled: bool
    username_configured: bool
    password_configured: bool

def get_redis_connection_settings() -> RedisConnectionSettings:
    ...
```

#### 2. Unit tests for config contract
**File**: `tests/test_config.py`
**Changes**:
- Add tests for precedence and split-vars fallback.
- Add tests for invalid port/db/type values and invalid URL scheme.
- Add tests that `rediss://`/`REDIS_TLS=true` combinations are accepted.
- Add tests that startup-style errors contain env variable names and do not contain password literals.

### Success Criteria:

#### Automated Verification:
- [x] `pytest -q tests/test_config.py`
- [x] New tests cover URL mode, split-vars mode, and invalid combinations.
- [x] `ruff check app/core/config.py tests/test_config.py`
- [x] `black --check app/core/config.py tests/test_config.py`

#### Manual Verification:
- [ ] Confirm config behavior with only `REDIS_URL` set.
- [ ] Confirm config behavior with only split vars set.
- [ ] Confirm invalid scheme (`http://...`) yields clear startup error.
- [ ] Confirm logs do not print raw `REDIS_PASSWORD`.

---

## Phase 2: Runtime Integration (JobStore, API Startup, Celery)

### Overview
Apply centralized Redis settings to runtime components and enforce API startup fail-fast connectivity validation.

### Changes Required:

#### 1. JobStore Redis initialization
**File**: `app/core/job_store.py`
**Changes**:
- Replace direct `REDIS_URL` read at `app/core/job_store.py:266` with config helper from Phase 1.
- Keep Redis client creation through one normalized URL or equivalent argument mapping.
- Keep current TTL/index semantics unchanged.
- Add explicit validation hook for startup that raises on ping failure (separate from `is_available()` boolean path used in `/health`).
- Ensure runtime logger still logs operational failures through existing structured style.

```python
def validate_redis_job_store_startup(store: JobStore) -> None:
    if isinstance(store, RedisJobStore) and not store.is_available():
        raise RuntimeError("Redis JobStore startup validation failed: ping returned unavailable")
```

#### 2. API startup fail-fast and safe startup logging
**File**: `app/main.py`
**Changes**:
- In startup event, run Redis startup validation for redis backend.
- Keep raising `RuntimeError` for fail-fast behavior aligned with existing HMAC pattern.
- Replace raw `redis_url` logging with masked/sanitized fields:
  - `redis_source`
  - `redis_tls_enabled`
  - `redis_username_configured`
  - `redis_password_configured`
  - optional masked URL/endpoint

#### 3. Celery broker/backend compatibility with shared Redis settings
**File**: `app/core/celery_app.py`
**Changes**:
- Preserve current precedence for explicit Celery vars:
  - `CELERY_BROKER_URL` overrides shared Redis settings.
  - `CELERY_RESULT_BACKEND` overrides broker fallback.
- When explicit Celery vars are absent, use normalized shared Redis URL from Phase 1 helper so split-vars mode works end-to-end.
- Keep all existing task config semantics unchanged.

#### 4. Runtime/integration tests
**Files**:
- `tests/test_config.py`
- `tests/test_api.py`
- `tests/test_contracts.py`
- `tests/test_job_store.py`
**Changes**:
- Add startup fail-fast test for redis backend with mocked ping failure.
- Add positive startup test with mocked ping success.
- Update tests that assume implicit startup success under redis backend to set `JOB_STORE_BACKEND=memory` or mock redis availability explicitly.
- Keep health contract shape unchanged.

### Success Criteria:

#### Automated Verification:
- [x] `pytest -q tests/test_job_store.py tests/test_api.py tests/test_contracts.py tests/test_config.py`
- [x] Startup fail-fast test fails before serving requests when Redis is unavailable.
- [x] `ruff check app/core/job_store.py app/main.py app/core/celery_app.py tests`
- [x] `black --check app/core/job_store.py app/main.py app/core/celery_app.py tests`

#### Manual Verification:
- [ ] With valid external Redis auth/TLS config, API starts and `/health` reports `job_store.available=true`.
- [ ] With invalid Redis credentials, API process exits during startup (no fallback).
- [ ] With valid split-vars config and empty `REDIS_URL`, job creation and polling still work.
- [ ] Startup logs show sanitized Redis config info only.

---

## Phase 3: Documentation and Environment Wiring

### Overview
Document and exemplify the new contract for local/test/production parity.

### Changes Required:

#### 1. Env examples and configuration templates
**Files**:
- `tools/runtime/.env.example`
- `config.toml.example`
**Changes**:
- Add split Redis variables and defaults.
- Document precedence: `REDIS_URL` first, split vars second.
- Provide TLS/auth examples using both `rediss://` URL and split vars.

#### 2. Runtime compose and monitoring notes
**Files**:
- `tools/runtime/docker-compose.yml`
- `tools/monitoring/docker-compose.yml`
**Changes**:
- Keep local compose behavior functional by default.
- Add comments/examples for external Redis usage.
- Note monitoring exporter auth/TLS considerations when Redis moves external.

#### 3. User-facing documentation
**Files**:
- `README.md`
- `README-DEV.md`
- `docs/architecture-celery-redis.md`
**Changes**:
- Extend configuration tables with new vars and precedence.
- Document startup fail-fast behavior and expected failure mode.
- Add security note about secret masking and avoiding raw credential logging.

### Success Criteria:

#### Automated Verification:
- [x] `ruff check .`
- [x] `black --check .`
- [x] `pytest -q`

#### Manual Verification:
- [ ] Developer can configure external Redis using URL mode from docs.
- [ ] Developer can configure external Redis using split-vars mode from docs.
- [ ] Local docker-compose setup remains runnable without additional mandatory secrets.
- [ ] Documentation consistently describes one shared Redis for API/Celery/JobStore.

---

## Testing Strategy

### Unit Tests:
- Config parsing and precedence for URL vs split vars.
- Redis URL validation and error messages (invalid scheme/type).
- Sanitization/masking behavior for startup log payload preparation.
- JobStore startup validation utility behavior on ping success/failure.

### Integration Tests:
- API startup fails fast when Redis backend is selected and ping fails.
- API startup succeeds with split-vars configuration and mocked available Redis.
- Existing async job flow remains unchanged under memory backend and redis backend test doubles.

### Manual Testing Steps:
1. Configure external Redis using `REDIS_URL=rediss://user:pass@host:port/0`, start API, verify startup and `/health`.
2. Remove `REDIS_URL`, set split vars including `REDIS_TLS=true`, restart API, verify same behavior.
3. Set incorrect password, restart API, verify startup failure with controlled error and no secret leakage in logs.
4. Run one end-to-end job (`POST /v1/compare/jobs` then poll) to confirm unchanged semantics.

## Performance Considerations

- Startup adds one Redis ping in redis backend mode; negligible runtime overhead.
- No change to request-path latency or Celery task processing logic.
- No additional retry loops added; existing semantics preserved by design.

## Migration Notes

- Backward compatible: existing `REDIS_URL` users continue working.
- Split-vars mode is additive.
- If both URL and split vars are present, URL wins (explicitly documented).
- Teams moving from local docker Redis to external service can migrate by env-only changes.

## References

- Original ticket: `thoughts/tickets/feature_redis_external_service_auth.md`
- Legacy input ticket: `ticket_001.md`
- Config precedence implementation: `app/core/config.py:56`
- JobStore Redis factory: `app/core/job_store.py:261`
- Celery Redis URL fallback: `app/core/celery_app.py:19`
- Startup settings log (to sanitize): `app/main.py:49`
- Existing startup fail-fast pattern: `app/core/hmac_auth.py:24`
