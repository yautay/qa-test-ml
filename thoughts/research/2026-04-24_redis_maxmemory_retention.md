---
date: 2026-04-24T17:37:58+02:00
git_commit: 509fd08536e067421fcb6f56c94ee3c5faf09fc6
branch: feature/NN-23952-pms-obsluzyc-w-kodzie-auth-dla-redis
repository: qa-test-pms
topic: "DEBT-002 unified job retention for Redis maxmemory resilience"
tags: [research, codebase, job-store, redis, api, observability]
last_updated: 2026-04-24
---

## Ticket Synopsis
Ticket DEBT-002 asks for a single retention model for compare jobs across `redis` and `memory` backends, with full cleanup of job state and artifacts, explicit API behavior for expired jobs (preferably `410 Gone`), and operational logging/metrics. It is explicitly app-layer scope (not Redis infra tuning), and asks for backward-safe rollout.

## Summary
Current retention is asymmetric: `RedisJobStore` applies TTLs for job and heatmap keys and lazily prunes stale index entries, while `MemoryJobStore` has no TTL/retention at all. API currently collapses missing and expired into `404` because store reads only return `JobState | None`. The least invasive architecture-compatible approach is lazy retention cleanup in store methods (especially for memory parity) plus explicit expired tracking at HTTP layer (without adding a new domain status) and new cleanup/expired observability counters/logs. Implemented direction: one canonical retention key (`JOB_RETENTION_SEC`), store tombstones, and `410` for known-expired jobs.

## Detailed Findings

### JobStore Retention and Cleanup
- Redis applies TTL on create (`SET ... EX`) for job payloads and heatmaps (`app/core/job_store.py:192`, `app/core/job_store.py:256`).
- Redis preserves TTL on updates by reading `ttl()` and reusing/falling back to configured TTL (`app/core/job_store.py:246`, `app/core/job_store.py:248`).
- Redis keeps job IDs in a zset index and lazily prunes stale IDs in `list_jobs()` (`app/core/job_store.py:195`, `app/core/job_store.py:226`, `app/core/job_store.py:228`).
- Memory backend stores jobs/heatmaps in in-process dicts with no expiration path (`app/core/job_store.py:124`, `app/core/job_store.py:125`, `app/core/job_store.py:138`).
- Retention config is now one canonical key (`JOB_RETENTION_SEC`) with default 86400 (`app/core/job_store.py`).

### API Contract for Missing vs Expired
- Job status endpoint returns `404` when store returns `None`; no expired distinction exists (`app/api/routes/compare.py:390`, `app/api/routes/compare.py:392`).
- Heatmap endpoint also returns `404` for multiple states: missing job, not-done job, and missing artifact (`app/api/routes/compare.py:435`, `app/api/routes/compare.py:438`, `app/api/routes/compare.py:441`).
- `/error` endpoint already uses state-aware status split (`404` for missing, `409` for wrong state), which is a good precedent for introducing expired-vs-not-found semantics (`app/api/routes/compare.py:465`, `app/api/routes/compare.py:467`).
- Domain status type allows only `queued|running|done|error`, so adding `expired` would require schema-wide domain changes (`app/schemas/compare.py:6`, `app/schemas/compare.py:47`).

### Runtime Flow and Cleanup Hooks
- App lifecycle sets shared `job_store` in FastAPI lifespan and validates Redis startup checks (`app/main.py:52`, `app/main.py:54`, `app/main.py:76`).
- Worker lifecycle updates store through `running/done/error`, so retention logic placed in `JobStore` naturally covers API and Celery paths (`app/tasks/compare_tasks.py:93`, `app/tasks/compare_tasks.py:141`, `app/tasks/compare_tasks.py:197`).
- Existing `_cleanup()` in task code only removes temporary local files, not job-store retention (`app/tasks/compare_tasks.py:59`, `app/tasks/compare_tasks.py:206`).

### Observability and Logging
- Prometheus currently tracks submissions, starts, finishes, failures, inflight, duration, and rejected requests; no cleanup/expired counters exist (`app/core/metrics.py:19`, `app/core/metrics.py:29`).
- Structured logging pattern uses `logger.bind(class_name, method_name, ...)` across API/tasks/store (`app/api/routes/compare.py:35`, `app/tasks/compare_tasks.py:115`, `app/core/job_store.py:290`).
- Worker metrics already follow lifecycle instrumentation pattern suitable for extension with cleanup/expired labels (`app/tasks/compare_tasks.py:89`, `app/tasks/compare_tasks.py:142`, `app/tasks/compare_tasks.py:198`, `app/tasks/compare_tasks.py:203`).

### Test Coverage and Gaps
- Store tests verify Redis stale-index pruning behavior (`tests/test_job_store.py:82`, `tests/test_job_store.py:95`).
- API tests assert current missing/error contracts (`404`/`409`) and heatmap-unavailable behavior (`tests/test_jobs_api.py:385`, `tests/test_jobs_api.py:391`, `tests/test_jobs_api.py:424`).
- Current tests do not cover memory-retention parity or explicit expired contract.

## Code References
- `app/core/job_store.py:120` - `MemoryJobStore` with in-memory dict persistence.
- `app/core/job_store.py:164` - `RedisJobStore` implementation and retention behavior.
- `app/core/job_store.py:192` - Job TTL application on create.
- `app/core/job_store.py:216` - `list_jobs()` index scan and stale-prune flow.
- `app/core/job_store.py` - `JOB_RETENTION_SEC` configuration read.
- `app/api/routes/compare.py:386` - Job status route (`404` on store miss).
- `app/api/routes/compare.py:430` - Heatmap route and current `404` contract.
- `app/api/routes/compare.py:459` - Error route showing `404` vs `409` split.
- `app/schemas/compare.py:6` - `JobStatusName` literals.
- `app/core/metrics.py:19` - Core Prometheus counters/gauge/histogram declarations.
- `app/tasks/compare_tasks.py:89` - Worker lifecycle metric emission pattern.
- `tests/test_job_store.py:82` - Redis stale-index prune test.
- `tests/test_jobs_api.py:388` - Missing job API contract test.

## Architecture Insights
- Retention belongs in `JobStore` as single source of truth because both API and Celery operate through it.
- Lazy cleanup is already an accepted pattern in this codebase (`list_jobs()` stale prune), making memory lazy-expiry a low-risk parity extension.
- Introducing `expired` as HTTP-level contract is less disruptive than expanding domain `JobStatusName` and downstream schema usage.
- Prometheus aggregate lifecycle metrics should remain cumulative; retention should add dedicated cleanup/expired signals, not retroactive metric deletion.

## Historical Context (from thoughts/)
- `thoughts/tickets/debt_redis_maxmemory_retention.md` - Source ticket defines unified retention, expired distinction, and observability requirements; infra maxmemory tuning stays out of scope.
- `thoughts/plans/debt_redis_auth_runtime_followups_implementation.md` - Confirms runtime wiring preference around FastAPI lifespan and safe startup behavior.
- `thoughts/reviews/debt_redis_auth_runtime_followups_implementation-review.md` - Validates lifecycle/startup approach and integration-test expectations.
- `thoughts/plans/feature_redis_external_service_auth_implementation.md` - Notes preserving existing TTL/index semantics while evolving runtime Redis wiring.

## Related Research
- `thoughts/tickets/debt_redis_maxmemory_retention.md`
- `thoughts/plans/debt_redis_auth_runtime_followups_implementation.md`
- `thoughts/reviews/debt_redis_auth_runtime_followups_implementation-review.md`
- `thoughts/plans/feature_redis_external_service_auth_implementation.md`

## Open Questions
- Should expired detection be modeled by tombstone metadata (to reliably return `410`) or by short-lived side index keyed by job id after cleanup?
- Should tombstone retention remain implicitly coupled to `JOB_RETENTION_SEC` by default, or become a hard-coded constant?
- Should `list_jobs()` (and maybe `get_job`) emit cleanup counters for stale-index removals in Redis and lazy-pruned entries in memory?
- Is heatmap retention required to be exactly equal to job retention, or can it remain separately configurable but default-coupled?
