# Validation Report: debt_redis_maxmemory_retention_implementation.md

## Scope Reviewed

- Plan file: `thoughts/plans/debt_redis_maxmemory_retention_implementation.md`
- Implementation commits reviewed:
  - `606ad61` (`fix: unify job retention semantics and return 410 for expired jobs`)
  - `b958f0d` (`docs: document DEBT-002 retention plan and clean obsolete notes`)
- Database/migrations: not applicable for this ticket (no schema changes planned or implemented).

## Implementation Status

- ✓ **Phase 1: Unified Retention and Tombstones in JobStore** - fully implemented.
  - `JobStore` contract extended with `is_job_expired(...)` (`app/core/job_store.py:115`).
  - Unified retention key in runtime wiring: `JOB_RETENTION_SEC` (`app/core/job_store.py:484`).
  - Memory backend now includes lazy expiration and tombstone lifecycle (`app/core/job_store.py:155`, `app/core/job_store.py:253`).
  - Redis backend includes tombstone keys and known-expired resolution (`app/core/job_store.py:285`, `app/core/job_store.py:395`).

- ✓ **Phase 2: API `410 Gone` Contract for Known-Expired Jobs** - fully implemented.
  - Shared missing-vs-expired helper added (`app/api/routes/compare.py:203`).
  - Status, heatmap, and error endpoints now map known-expired to `410` (`app/api/routes/compare.py:405`, `app/api/routes/compare.py:450`, `app/api/routes/compare.py:480`).
  - OpenAPI responses include `410` on all three endpoints (`app/api/routes/compare.py:394`, `app/api/routes/compare.py:439`, `app/api/routes/compare.py:468`).

- ✓ **Phase 3: Retention Observability (Metrics + Logs)** - fully implemented.
  - New counters added for cleanup, cleanup failures, and expired reads (`app/core/metrics.py:34`, `app/core/metrics.py:39`, `app/core/metrics.py:44`).
  - Store cleanup emits metrics/logs in memory and Redis paths (`app/core/job_store.py:149`, `app/core/job_store.py:336`, `app/core/job_store.py:353`).
  - Route-level expired-read metric + log added (`app/api/routes/compare.py:207`, `app/api/routes/compare.py:208`).

- ✓ **Phase 4: Tests, Examples, and Retention Config Migration** - fully implemented.
  - Tests added/updated in planned files (`tests/test_job_store.py`, `tests/test_jobs_api.py`, `tests/test_config.py`).
  - Runtime examples migrated to canonical retention key (`config.toml.example:30`, `tools/runtime/.env.example:29`).
  - Thought docs aligned (`thoughts/tickets/debt_redis_maxmemory_retention.md`, `thoughts/research/2026-04-24_redis_maxmemory_retention.md`).

## Automated Verification Results

All plan-listed automated checks were executed in this review and passed:

- ✓ `pytest -q tests/test_job_store.py` -> `15 passed`
- ✓ `ruff check app/core/job_store.py tests/test_job_store.py`
- ✓ `black --check app/core/job_store.py tests/test_job_store.py`
- ✓ `pytest -q tests/test_jobs_api.py` -> `19 passed`
- ✓ `ruff check app/api/routes/compare.py tests/test_jobs_api.py`
- ✓ `black --check app/api/routes/compare.py tests/test_jobs_api.py`
- ✓ `pytest -q tests/test_api.py tests/test_jobs_api.py` -> `24 passed`
- ✓ `ruff check app/core/metrics.py app/core/job_store.py app/api/routes/compare.py tests`
- ✓ `black --check app/core/metrics.py app/core/job_store.py app/api/routes/compare.py tests`
- ✓ `pytest -q` -> `64 passed, 3 deselected`
- ✓ `ruff check .`
- ✓ `black --check .`
- ✓ `mypy .` -> `Success: no issues found in 37 source files`

Note: `black --check` prints an environment warning about the local runtime Python being 3.10 while source targets 3.12, but all files are reported unchanged and checks pass.

## Code Review Findings

### Matches Plan

- Unified retention semantics are implemented for both job state and heatmap artifacts.
- Known-expired detection is implemented via tombstones in both backends and surfaced as `410` in all planned read endpoints.
- Existing non-expiry semantics are preserved:
  - Unknown missing IDs remain `404`.
  - `/error` wrong-state remains `409`.
  - Heatmap unavailable while job exists remains `404`.
- Cleanup/index hygiene instrumentation is present and tested.

### Deviations from Plan

- **Phase 1 (documented in plan)**: Added optional `JOB_TOMBSTONE_RETENTION_SEC` in addition to canonical `JOB_RETENTION_SEC` (`app/core/job_store.py:485`).
  - **Assessment**: Justified; enables bounded and explicit tombstone window while preserving one-key retention for job/heatmap artifacts.
  - **Impact**: Low risk, backward-safe default (`JOB_TOMBSTONE_RETENTION_SEC` defaults to `JOB_RETENTION_SEC`).

- **Additional deviation not called out in plan text**: `tests/test_redis_auth_integration.py` received a minor mypy-oriented `cast(...)` return typing fix in the same implementation commit.
  - **Assessment**: Benign and quality-improving; does not affect DEBT-002 runtime behavior.

### Potential Issues / Edge Cases

- No blocking defects found in implemented scope.
- Manual validation is still needed for real runtime/logs parity under both backends and for retention-disabled deployments (`JOB_RETENTION_SEC<=0`) to confirm operational behavior in target environments.

## Manual Testing Required

1. Backend parity and expiry behavior
   - [ ] Run with `JOB_STORE_BACKEND=memory`, create a job, wait past retention, verify `410` on status/heatmap/error while tombstone window is active.
   - [ ] Repeat with `JOB_STORE_BACKEND=redis` and verify parity.
2. Contract correctness checks
   - [ ] Verify random never-seen UUID still returns `404`.
   - [ ] Verify non-error job still returns `409` on `/error`.
3. Observability checks
   - [ ] Verify `/metrics` exposes `pms_retention_cleanup_total`, `pms_retention_cleanup_failures_total`, and `pms_expired_job_reads_total` after expiry scenarios.
   - [ ] Verify logs distinguish expired-read path and cleanup-failure path without exposing sensitive payload data.

## Recommendations

- Keep `JOB_TOMBSTONE_RETENTION_SEC` documented in runtime guides so operators understand the 410 visibility window.
- Consider adding one explicit test covering `JOB_RETENTION_SEC=0` + `JOB_TOMBSTONE_RETENTION_SEC=0` semantics to lock in disabled-retention behavior.
- Proceed to manual verification checklist before final release sign-off.
