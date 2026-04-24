# DEBT-002 Unified Job Retention for Redis Maxmemory Resilience Implementation Plan

## Overview

Implement a single retention contract for compare jobs across `memory` and `redis` backends using tombstone-based expiration tracking, return `410 Gone` for known-expired jobs across all job read endpoints, and add cleanup/expiration observability.

## Current State Analysis

Retention behavior is currently asymmetric and API semantics cannot distinguish expired from never-existing jobs.

- `MemoryJobStore` has no expiration path for jobs or heatmaps and stores data indefinitely in process memory (`app/core/job_store.py:123`, `app/core/job_store.py:156`).
- `RedisJobStore` applies TTL to job and heatmap keys and lazily prunes stale IDs from the sorted index during list reads (`app/core/job_store.py:192`, `app/core/job_store.py:216`, `app/core/job_store.py:256`).
- The API maps `store.get_job(...) is None` to `404` in status, heatmap, and error endpoints, with no known-expired distinction (`app/api/routes/compare.py:390`, `app/api/routes/compare.py:435`, `app/api/routes/compare.py:464`).
- Existing observability has job lifecycle counters and request rejection counters but no dedicated retention/cleanup/expired counters (`app/core/metrics.py:19`).
- Current retention config is split across `JOB_TTL_SEC` and `HEATMAP_TTL_SEC`, both defaulting to 86400 seconds (`app/core/job_store.py:350`, `app/core/job_store.py:351`).

## Desired End State

After implementation:

- One retention environment key controls retention behavior for both job state and heatmap artifacts.
- Retention semantics are behaviorally consistent between `memory` and `redis` backends.
- Job data cleanup includes job state, heatmap artifact data, and backend index hygiene.
- Tombstones allow known-expired detection after cleanup and before tombstone expiry.
- `GET /v1/compare/jobs/{job_id}`, `GET /v1/compare/jobs/{job_id}/heatmap`, and `GET /v1/compare/jobs/{job_id}/error` return `410` when a job is known expired; unknown missing jobs remain `404`.
- Logging and metrics expose cleanup activity, known-expired read attempts, and cleanup failures.

Verification target:

- For both backends, a job transitions from readable to expired and then returns `410` on read endpoints while tombstone is present.
- Existing non-expiry state semantics remain intact (`409` for non-error `/error`, `404` for heatmap unavailable while job exists and is non-done).

### Key Discoveries:
- Current API state-splitting precedent already exists in `/error` (`404` vs `409`), so adding `410` follows current style (`app/api/routes/compare.py:464`, `app/api/routes/compare.py:467`).
- Redis index stale-ID cleanup is already lazy, and that pattern can be reused for parity-safe cleanup in memory (`app/core/job_store.py:216`).
- Domain `JobStatusName` does not include `expired`, so HTTP-level distinction is lower-risk than schema expansion (`app/schemas/compare.py:6`).

## What We're NOT Doing

- No infrastructure-level Redis `maxmemory`/eviction-policy changes.
- No introduction of a new domain job status value `expired` in `JobStatusName`.
- No change to compare metric computation logic or Celery queue routing behavior.
- No broad redesign of health endpoint payloads or startup lifecycle semantics.
- No non-retention-related refactor in job submission flow.

## Implementation Approach

Implement expiration state as a store-level concern by extending `JobStore` with known-expired detection, then map expired state to `410` at the route layer. Keep existing `JobState` and response schemas intact. Introduce one canonical retention config key and remove split retention-key behavior from runtime logic. Keep cleanup lazy and operation-triggered to avoid adding schedulers in this ticket.

## Phase 1: Unified Retention and Tombstones in JobStore

### Overview
Create one retention model in `JobStore` across backends, with equal retention for job and heatmap data and tombstone tracking for known-expired detection.

### Changes Required:

#### 1. JobStore interface and expiration contract
**File**: `app/core/job_store.py`
**Changes**:
- Add explicit store contract for known-expired detection (for example `is_job_expired(job_id: str) -> bool`).
- Keep existing `get_job`/`get_heatmap` signatures to minimize route and worker churn.
- Add backend-specific tombstone storage with a bounded retention window.

```python
class JobStore:
    def is_job_expired(self, job_id: str) -> bool:
        raise NotImplementedError
```

#### 2. Single retention key and equal retention behavior
**File**: `app/core/job_store.py`
**Changes**:
- Replace split runtime env reads (`JOB_TTL_SEC`, `HEATMAP_TTL_SEC`) with one retention env key (for example `JOB_RETENTION_SEC`) in `create_job_store()`.
- Apply the same retention value to job and heatmap retention behavior in both backends.
- Keep `<=0` behavior explicit and deterministic (no accidental expiry when disabled).

#### 3. Memory backend parity
**File**: `app/core/job_store.py`
**Changes**:
- Add retention bookkeeping for memory jobs (expiry timestamps and tombstone map).
- Implement lazy prune during read/list/write operations:
  - remove expired job state,
  - remove associated heatmap,
  - record tombstone entry.
- Prune stale tombstones lazily to prevent unbounded tombstone growth.

#### 4. Redis backend tombstones and retention alignment
**File**: `app/core/job_store.py`
**Changes**:
- Add tombstone key namespace per job ID.
- Ensure known-expired detection can be resolved after job key expiry and before tombstone expiry.
- Keep stale index pruning in `list_jobs()` and ensure cleanup does not regress current behavior.
- Align heatmap retention to job retention semantics to satisfy equal retention requirement.

### Success Criteria:

#### Automated Verification:
- [x] Unit tests pass for store behavior: `pytest -q tests/test_job_store.py`
- [x] New tests cover memory retention + tombstones + lazy cleanup.
- [x] New tests cover redis tombstone expired detection + stale index hygiene parity.
- [x] Lint passes for store changes: `ruff check app/core/job_store.py tests/test_job_store.py`
- [x] Format check passes: `black --check app/core/job_store.py tests/test_job_store.py`

#### Manual Verification:
- [ ] With `JOB_STORE_BACKEND=memory`, expired jobs are removed and later reads can be identified as known-expired.
- [ ] With `JOB_STORE_BACKEND=redis`, job and heatmap expiration behavior is consistent and known-expired detection works.
- [ ] Job listing does not accumulate stale entries over repeated create/expire/list cycles.
- [ ] Retention disabled mode (if configured) behaves explicitly and predictably.

---

## Phase 2: API `410 Gone` Contract for Known-Expired Jobs

### Overview
Update job read endpoints to distinguish unknown-missing (`404`) from known-expired (`410`) using store tombstones.

### Changes Required:

#### 1. Shared route-level missing vs expired decision
**File**: `app/api/routes/compare.py`
**Changes**:
- Introduce helper logic that checks store expiry marker when `get_job(...)` returns `None`.
- Return `410` when `store.is_job_expired(job_id)` is true; otherwise keep `404`.

```python
job = store.get_job(job_id)
if job is None:
    if store.is_job_expired(job_id):
        raise HTTPException(status_code=410, detail=f"Job expired: {job_id}")
    raise HTTPException(status_code=404, detail=f"Job not found: {job_id}")
```

#### 2. Apply `410` contract to all job read endpoints
**File**: `app/api/routes/compare.py`
**Changes**:
- Apply known-expired handling in:
  - `GET /v1/compare/jobs/{job_id}`
  - `GET /v1/compare/jobs/{job_id}/heatmap`
  - `GET /v1/compare/jobs/{job_id}/error`
- Keep existing non-expiry semantics unchanged:
  - `/error` still returns `409` for non-error state.
  - `/heatmap` still returns `404` for unavailable heatmap when job exists but is not eligible.

#### 3. OpenAPI response contract updates
**File**: `app/api/routes/compare.py`
**Changes**:
- Add `410` response descriptions to all three read endpoints.
- Preserve existing `404` descriptions for unknown-missing resources.

### Success Criteria:

#### Automated Verification:
- [x] API tests pass for changed contract: `pytest -q tests/test_jobs_api.py`
- [x] New API tests verify `410` on known-expired for status, heatmap, and error endpoints.
- [x] Existing tests for `404` unknown-missing and `409` wrong-state still pass.
- [x] Lint passes for route changes: `ruff check app/api/routes/compare.py tests/test_jobs_api.py`
- [x] Format check passes: `black --check app/api/routes/compare.py tests/test_jobs_api.py`

#### Manual Verification:
- [ ] Polling a recently expired known job returns `410` in status endpoint.
- [ ] Heatmap and error endpoints also return `410` for the same known-expired job.
- [ ] A random never-seen UUID still returns `404`.
- [ ] A non-error job still returns `409` on `/error`.

---

## Phase 3: Retention Observability (Metrics + Structured Logs)

### Overview
Expose cleanup and expiration behavior as first-class operational signals.

### Changes Required:

#### 1. Prometheus metrics for cleanup and expiry reads
**File**: `app/core/metrics.py`
**Changes**:
- Add counters for:
  - cleanup executions/removals by backend and artifact type,
  - known-expired read detections,
  - cleanup failures.
- Keep existing lifecycle counters unchanged.

#### 2. Emit metrics and logs from store cleanup paths
**File**: `app/core/job_store.py`
**Changes**:
- Emit metrics where expiration cleanup actually occurs (memory lazy prune and redis stale/index/tombstone handling).
- Add structured logs using existing `logger.bind(...)` pattern, including backend, job_id, action, and outcome.
- Use warning/error levels only for real cleanup failures.

#### 3. Route-level observability for expired reads
**File**: `app/api/routes/compare.py`
**Changes**:
- Add lightweight logging for `410` decisions with endpoint and job ID context.
- Avoid sensitive data in logs.

### Success Criteria:

#### Automated Verification:
- [x] Metrics module imports and app startup remain healthy: `pytest -q tests/test_api.py tests/test_jobs_api.py`
- [x] New tests assert main cleanup/expired counters increment in representative paths.
- [x] Lint passes for observability code: `ruff check app/core/metrics.py app/core/job_store.py app/api/routes/compare.py tests`
- [x] Format check passes: `black --check app/core/metrics.py app/core/job_store.py app/api/routes/compare.py tests`

#### Manual Verification:
- [ ] `/metrics` exposes new retention counters after expiration scenarios.
- [ ] Logs clearly differentiate unknown-missing vs known-expired vs cleanup error.
- [ ] No secrets or payload data leak in cleanup/expiration logs.

---

## Phase 4: Tests, Examples, and Retention Config Migration

### Overview
Update automated coverage and runtime examples for the one-key retention model.

### Changes Required:

#### 1. Unit and API test additions/updates
**Files**:
- `tests/test_job_store.py`
- `tests/test_jobs_api.py`
- `tests/test_config.py`
**Changes**:
- Add targeted tests for one-key retention behavior.
- Add known-expired `410` tests on all three read endpoints.
- Ensure cache clearing in tests remains correct when env vars change.

#### 2. Runtime config examples
**Files**:
- `config.toml.example`
- `tools/runtime/.env.example`
**Changes**:
- Replace split retention key examples with the canonical one-key retention setting.
- Keep examples consistent with equal job/heatmap retention semantics.

#### 3. Thought docs alignment
**Files**:
- `thoughts/tickets/debt_redis_maxmemory_retention.md`
- `thoughts/research/2026-04-24_redis_maxmemory_retention.md`
**Changes**:
- Align retention key naming and expected API contract examples with implemented direction.

### Success Criteria:

#### Automated Verification:
- [x] Full fast test pass: `pytest -q`
- [x] Lint passes repo-wide: `ruff check .`
- [x] Format check passes repo-wide: `black --check .`
- [x] Type checks pass repo-wide: `mypy .`

## Deviations from Plan

### Phase 1: Unified Retention and Tombstones in JobStore
- **Original Plan**: Introduce a single retention key for runtime behavior.
- **Actual Implementation**: Implemented canonical `JOB_RETENTION_SEC` for job and heatmap retention, plus optional `JOB_TOMBSTONE_RETENTION_SEC` (defaulting to retention) to bound known-expired tombstone lifetime.
- **Reason for Deviation**: Tombstones must outlive job state briefly to return `410` after cleanup; making this explicit keeps behavior deterministic while preserving one-key retention for artifacts.
- **Impact Assessment**: No change to job/heatmap retention contract; adds an optional knob for tombstone window tuning with backward-safe defaults.
- **Date/Time**: 2026-04-24

#### Manual Verification:
- [ ] A developer can configure retention with a single env key and observe the same behavior in memory and redis modes.
- [ ] API clients can clearly differentiate unknown-missing (`404`) from known-expired (`410`).
- [ ] Existing non-retention flows (job submission, done/error transitions) are not regressed.

---

## Testing Strategy

### Unit Tests:
- `JobStore` contract for active vs known-expired vs unknown-missing.
- Memory lazy prune correctness for job + heatmap + tombstone lifecycle.
- Redis tombstone lifecycle and stale-index cleanup interaction.
- One-key retention config read path.

### Integration Tests:
- API-level end-to-end tests for `410` behavior across status/heatmap/error.
- Backend parity tests for memory and redis retention behavior.

### Manual Testing Steps:
1. Start with `JOB_STORE_BACKEND=memory`, submit a job, wait past retention, and verify `410` on all three read endpoints.
2. Repeat with `JOB_STORE_BACKEND=redis` and verify parity.
3. Query with random UUIDs and verify `404` for unknown IDs.
4. Verify `/metrics` includes new cleanup/expired signals after expiry scenarios.

## Performance Considerations

- Lazy cleanup avoids new background schedulers but adds small per-operation pruning overhead.
- Tombstone storage introduces additional key/map operations; bounded tombstone retention prevents unbounded growth.
- Redis index pruning remains lazy and should remain operationally cheap under normal list frequency.

## Migration Notes

- Existing deployments using split retention keys must migrate to the canonical retention key.
- Rollout should prioritize backward-safe behavior in one release window, then remove split-key usage.
- If retention is configured too low relative to task runtime, worker updates can fail on missing jobs; enforce operationally safe defaults.

## References

- Original ticket: `thoughts/tickets/debt_redis_maxmemory_retention.md`
- Related research: `thoughts/research/2026-04-24_redis_maxmemory_retention.md`
- Similar lifecycle pattern: `app/api/routes/compare.py:464`
- Store implementations: `app/core/job_store.py:120`
- API read routes: `app/api/routes/compare.py:386`
- Metrics declarations: `app/core/metrics.py:19`
