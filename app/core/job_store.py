from __future__ import annotations

import json
import threading
import time
from collections.abc import Iterable
from dataclasses import dataclass
from functools import lru_cache
from typing import TYPE_CHECKING, Any, cast
from uuid import uuid4

from loguru import logger

if TYPE_CHECKING:
    pass

try:
    import redis as redis_lib

    _HAS_REDIS = True
except ImportError:  # pragma: no cover
    redis_lib = None  # type: ignore[assignment]
    _HAS_REDIS = False

from app.core.config import get_int, get_redis_connection_settings, get_str
from app.core.metrics import retention_cleanup_failures_total, retention_cleanup_total
from app.schemas.compare import JobMetricName, JobStatusName

_REDIS_STARTUP_CHECK_ALLOWED_MODES = {"ping", "rw", "none"}


def get_redis_startup_check_mode() -> str:
    mode = get_str("REDIS_STARTUP_CHECK_MODE", "ping").strip().lower() or "ping"
    if mode not in _REDIS_STARTUP_CHECK_ALLOWED_MODES:
        raise RuntimeError("REDIS_STARTUP_CHECK_MODE must be one of: ping, rw, none")
    return mode


@dataclass
class JobState:
    job_id: str
    pair_id: str
    metric: JobMetricName
    model: str
    normalize: bool
    img_a_name: str
    img_b_name: str
    status: JobStatusName
    lpips: float | None = None
    dists: float | None = None
    timing_ms: int | None = None
    error_message: str | None = None
    has_heatmap: bool = False
    created_at_ms: int = 0

    def to_dict(self) -> dict[str, object]:
        return {
            "job_id": self.job_id,
            "pair_id": self.pair_id,
            "metric": self.metric,
            "model": self.model,
            "normalize": self.normalize,
            "img_a_name": self.img_a_name,
            "img_b_name": self.img_b_name,
            "status": self.status,
            "lpips": self.lpips,
            "dists": self.dists,
            "timing_ms": self.timing_ms,
            "error_message": self.error_message,
            "has_heatmap": self.has_heatmap,
            "created_at_ms": self.created_at_ms,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> JobState:
        return cls(
            job_id=str(data["job_id"]),
            pair_id=str(data["pair_id"]),
            metric=cast(JobMetricName, data["metric"]),
            model=str(data["model"]),
            normalize=bool(data["normalize"]),
            img_a_name=str(data.get("img_a_name", "img_a.png")),
            img_b_name=str(data.get("img_b_name", "img_b.png")),
            status=cast(JobStatusName, data["status"]),
            lpips=float(data["lpips"]) if data.get("lpips") is not None else None,
            dists=float(data["dists"]) if data.get("dists") is not None else None,
            timing_ms=int(data["timing_ms"]) if data.get("timing_ms") is not None else None,
            error_message=(str(data["error_message"]) if data.get("error_message") is not None else None),
            has_heatmap=bool(data.get("has_heatmap", False)),
            created_at_ms=int(data.get("created_at_ms", 0)),
        )


class JobStore:
    backend_name: str = "unknown"

    def create_job(self, job: JobState) -> None:
        raise NotImplementedError

    def get_job(self, job_id: str) -> JobState | None:
        raise NotImplementedError

    def list_jobs(self) -> list[JobState]:
        raise NotImplementedError

    def update_job(self, job_id: str, **fields: object) -> JobState:
        raise NotImplementedError

    def set_heatmap(self, job_id: str, heatmap_png: bytes) -> None:
        raise NotImplementedError

    def get_heatmap(self, job_id: str) -> bytes | None:
        raise NotImplementedError

    def is_job_expired(self, job_id: str) -> bool:
        raise NotImplementedError

    def is_available(self) -> bool:
        raise NotImplementedError


class MemoryJobStore(JobStore):
    backend_name = "memory"

    def __init__(self, *, retention_sec: int = 86400, tombstone_retention_sec: int | None = None):
        self._retention_sec = max(0, retention_sec)
        self._retention_ms = self._retention_sec * 1000
        tombstone_sec = self._retention_sec if tombstone_retention_sec is None else tombstone_retention_sec
        self._tombstone_retention_sec = max(0, tombstone_sec)
        self._tombstone_retention_ms = self._tombstone_retention_sec * 1000
        self._jobs: dict[str, JobState] = {}
        self._heatmaps: dict[str, bytes] = {}
        self._expires_at_ms: dict[str, int] = {}
        self._tombstones: dict[str, int] = {}
        self._lock = threading.Lock()

    def _record_tombstone_locked(self, job_id: str, *, now: int) -> None:
        if self._tombstone_retention_ms <= 0:
            return
        self._tombstones[job_id] = now + self._tombstone_retention_ms

    def _prune_tombstones_locked(self, *, now: int) -> None:
        if not self._tombstones:
            return
        stale_job_ids = [job_id for job_id, tombstone_expiry in self._tombstones.items() if tombstone_expiry <= now]
        for job_id in stale_job_ids:
            self._tombstones.pop(job_id, None)
        if stale_job_ids:
            retention_cleanup_total.labels(
                backend=self.backend_name,
                artifact="tombstone",
                outcome="pruned",
            ).inc(len(stale_job_ids))

    def _prune_expired_jobs_locked(self, *, now: int, job_id: str | None = None) -> None:
        if self._retention_ms <= 0 or not self._expires_at_ms:
            return

        if job_id is None:
            candidate_ids = list(self._expires_at_ms.keys())
        elif job_id in self._expires_at_ms:
            candidate_ids = [job_id]
        else:
            candidate_ids = []

        for candidate_id in candidate_ids:
            expires_at = self._expires_at_ms.get(candidate_id)
            if expires_at is None or expires_at > now:
                continue
            job_existed = self._jobs.pop(candidate_id, None) is not None
            heatmap_existed = self._heatmaps.pop(candidate_id, None) is not None
            self._expires_at_ms.pop(candidate_id, None)
            self._record_tombstone_locked(candidate_id, now=now)
            if job_existed:
                retention_cleanup_total.labels(
                    backend=self.backend_name,
                    artifact="job_state",
                    outcome="expired",
                ).inc()
            if heatmap_existed:
                retention_cleanup_total.labels(
                    backend=self.backend_name,
                    artifact="heatmap",
                    outcome="expired",
                ).inc()
            logger.bind(
                class_name="MemoryJobStore",
                method_name="_prune_expired_jobs_locked",
                backend=self.backend_name,
                job_id=candidate_id,
                action="expire",
                outcome="removed",
            ).debug("Expired in-memory job state was pruned")

    def _prune_locked(self, *, job_id: str | None = None) -> None:
        try:
            now = now_ms()
            self._prune_expired_jobs_locked(now=now, job_id=job_id)
            self._prune_tombstones_locked(now=now)
        except Exception as exc:
            retention_cleanup_failures_total.labels(backend=self.backend_name, action="lazy_prune").inc()
            logger.bind(
                class_name="MemoryJobStore",
                method_name="_prune_locked",
                backend=self.backend_name,
                job_id=job_id,
                action="lazy_prune",
                outcome="failure",
            ).opt(exception=exc).warning("Memory retention cleanup failed")
            raise

    def create_job(self, job: JobState) -> None:
        with self._lock:
            self._prune_locked(job_id=job.job_id)
            if job.job_id in self._jobs:
                raise ValueError(f"Job already exists: {job.job_id}")
            self._jobs[job.job_id] = job
            self._tombstones.pop(job.job_id, None)
            if self._retention_ms > 0:
                self._expires_at_ms[job.job_id] = now_ms() + self._retention_ms

    def get_job(self, job_id: str) -> JobState | None:
        with self._lock:
            self._prune_locked(job_id=job_id)
            return self._jobs.get(job_id)

    def list_jobs(self) -> list[JobState]:
        with self._lock:
            self._prune_locked()
            values = list(self._jobs.values())
        return sorted(values, key=lambda item: item.created_at_ms)

    def update_job(self, job_id: str, **fields: object) -> JobState:
        with self._lock:
            self._prune_locked(job_id=job_id)
            job = self._jobs[job_id]
            for key, value in fields.items():
                setattr(job, key, value)
            return job

    def set_heatmap(self, job_id: str, heatmap_png: bytes) -> None:
        with self._lock:
            self._prune_locked(job_id=job_id)
            self._heatmaps[job_id] = heatmap_png
            if job_id in self._jobs:
                self._jobs[job_id].has_heatmap = True

    def get_heatmap(self, job_id: str) -> bytes | None:
        with self._lock:
            self._prune_locked(job_id=job_id)
            return self._heatmaps.get(job_id)

    def is_job_expired(self, job_id: str) -> bool:
        with self._lock:
            self._prune_locked(job_id=job_id)
            return job_id in self._tombstones

    def is_available(self) -> bool:
        return True


class RedisJobStore(JobStore):
    backend_name = "redis"

    def __init__(
        self,
        redis_client: Any,
        *,
        prefix: str,
        retention_sec: int,
        tombstone_retention_sec: int | None = None,
    ):
        self._redis = redis_client
        self._prefix = prefix
        self._retention_sec = max(0, retention_sec)
        tombstone_sec = self._retention_sec if tombstone_retention_sec is None else tombstone_retention_sec
        self._tombstone_retention_sec = max(0, tombstone_sec)

    def _job_key(self, job_id: str) -> str:
        return f"{self._prefix}:job:{job_id}"

    def _heatmap_key(self, job_id: str) -> str:
        return f"{self._prefix}:job:{job_id}:heatmap"

    def _tombstone_key(self, job_id: str) -> str:
        return f"{self._prefix}:job:{job_id}:expired"

    def _jobs_index_key(self) -> str:
        return f"{self._prefix}:jobs:index"

    def create_job(self, job: JobState) -> None:
        key = self._job_key(job.job_id)
        payload = json.dumps(job.to_dict())
        created = self._redis.set(key, payload, nx=True, ex=self._retention_sec or None)
        if not created:
            raise ValueError(f"Job already exists: {job.job_id}")
        self._redis.zadd(self._jobs_index_key(), {job.job_id: float(job.created_at_ms)})
        if self._tombstone_retention_sec > 0:
            self._redis.set(
                self._tombstone_key(job.job_id), "1", ex=self._retention_sec + self._tombstone_retention_sec
            )

    def _parse_jobs(self, rows: Iterable[bytes | str]) -> list[JobState]:
        out: list[JobState] = []
        for row in rows:
            payload = row.decode("utf-8") if isinstance(row, bytes) else row
            data = json.loads(payload)
            if isinstance(data, dict):
                out.append(JobState.from_dict(data))
        return out

    def get_job(self, job_id: str) -> JobState | None:
        row = self._redis.get(self._job_key(job_id))
        if row is None:
            return None
        payload = row.decode("utf-8") if isinstance(row, bytes) else row
        data = json.loads(payload)
        if not isinstance(data, dict):
            return None
        return JobState.from_dict(data)

    def list_jobs(self) -> list[JobState]:
        index_key = self._jobs_index_key()
        try:
            ids = self._redis.zrange(index_key, 0, -1)
            if not ids:
                return []

            normalized_ids = [job_id.decode("utf-8") if isinstance(job_id, bytes) else str(job_id) for job_id in ids]
            keys = [self._job_key(job_id) for job_id in normalized_ids]
            rows = self._redis.mget(keys)

            stale_ids = [job_id for job_id, row in zip(normalized_ids, rows, strict=False) if row is None]
            if stale_ids:
                self._redis.zrem(index_key, *stale_ids)
                retention_cleanup_total.labels(
                    backend=self.backend_name,
                    artifact="jobs_index",
                    outcome="pruned",
                ).inc(len(stale_ids))
                logger.bind(
                    class_name="RedisJobStore",
                    method_name="list_jobs",
                    backend=self.backend_name,
                    action="stale_index_prune",
                    outcome="removed",
                    count=len(stale_ids),
                ).debug("Pruned stale job index entries")

            valid_rows = [row for row in rows if row is not None]
            return self._parse_jobs(valid_rows)
        except Exception as exc:
            retention_cleanup_failures_total.labels(backend=self.backend_name, action="list_jobs").inc()
            logger.bind(
                class_name="RedisJobStore",
                method_name="list_jobs",
                backend=self.backend_name,
                action="stale_index_prune",
                outcome="failure",
            ).opt(exception=exc).warning("Redis retention cleanup failed during list_jobs")
            raise

    def update_job(self, job_id: str, **fields: object) -> JobState:
        key = self._job_key(job_id)
        row = self._redis.get(key)
        if row is None:
            raise KeyError(job_id)
        payload = row.decode("utf-8") if isinstance(row, bytes) else row
        data = json.loads(payload)
        if not isinstance(data, dict):
            raise KeyError(job_id)

        data.update(fields)
        payload = json.dumps(data)

        ttl = self._redis.ttl(key)
        ex = ttl if ttl > 0 else (self._retention_sec or None)
        self._redis.set(key, payload, ex=ex)

        updated = self.get_job(job_id)
        if updated is None:
            raise KeyError(job_id)
        return updated

    def set_heatmap(self, job_id: str, heatmap_png: bytes) -> None:
        job_ttl = self._redis.ttl(self._job_key(job_id))
        ex = job_ttl if job_ttl > 0 else (self._retention_sec or None)
        self._redis.set(self._heatmap_key(job_id), heatmap_png, ex=ex)
        self.update_job(job_id, has_heatmap=True)

    def get_heatmap(self, job_id: str) -> bytes | None:
        result = self._redis.get(self._heatmap_key(job_id))
        return cast(bytes | None, result)

    def is_job_expired(self, job_id: str) -> bool:
        if self._tombstone_retention_sec <= 0:
            return False
        if self._redis.exists(self._job_key(job_id)):
            return False
        return bool(self._redis.exists(self._tombstone_key(job_id)))

    def _rw_probe(self) -> None:
        probe_key = f"{self._prefix}:startup:probe:{uuid4().hex}"
        probe_value = uuid4().hex

        created = self._redis.set(probe_key, probe_value, ex=30)
        if not created:
            raise RuntimeError("Redis JobStore startup validation failed: rw probe key was not written")

        row = self._redis.get(probe_key)
        if row is None:
            raise RuntimeError("Redis JobStore startup validation failed: rw probe key was not readable")

        payload = row.decode("utf-8") if isinstance(row, bytes) else str(row)
        if payload != probe_value:
            raise RuntimeError("Redis JobStore startup validation failed: rw probe value mismatch")

        self._redis.delete(probe_key)

    def is_available(self) -> bool:
        mode = get_redis_startup_check_mode()
        if mode == "none":
            return True
        if mode == "rw":
            try:
                self._rw_probe()
                return True
            except Exception as exc:
                logger.bind(class_name="RedisJobStore", method_name="is_available").opt(exception=exc).warning(
                    "Redis rw availability probe failed"
                )
                return False

        try:
            return bool(self._redis.ping())
        except Exception as exc:
            logger.bind(class_name="RedisJobStore", method_name="is_available").opt(exception=exc).warning(
                "Redis ping failed"
            )
            return False

    def _validate_startup_ping(self) -> None:
        try:
            if not self._redis.ping():
                raise RuntimeError("Redis JobStore startup validation failed: ping returned unavailable")
        except RuntimeError:
            raise
        except Exception as exc:
            logger.bind(class_name="RedisJobStore", method_name="validate_startup").opt(exception=exc).warning(
                "Redis startup ping failed"
            )
            raise RuntimeError("Redis JobStore startup validation failed: ping raised an exception") from exc

    def _validate_startup_rw(self) -> None:
        try:
            self._rw_probe()
        except RuntimeError:
            raise
        except Exception as exc:
            logger.bind(class_name="RedisJobStore", method_name="validate_startup").opt(exception=exc).warning(
                "Redis startup rw probe failed"
            )
            raise RuntimeError("Redis JobStore startup validation failed: rw check raised an exception") from exc

    def validate_startup(self, *, mode: str = "ping") -> None:
        if mode == "none":
            logger.bind(class_name="RedisJobStore", method_name="validate_startup").warning(
                "Redis startup validation skipped (REDIS_STARTUP_CHECK_MODE=none)"
            )
            return
        if mode == "rw":
            self._validate_startup_rw()
            return
        self._validate_startup_ping()


def validate_redis_job_store_startup(store: JobStore) -> None:
    if isinstance(store, RedisJobStore):
        store.validate_startup(mode=get_redis_startup_check_mode())


def create_job_store() -> JobStore:
    backend = get_str("JOB_STORE_BACKEND", "redis").strip().lower()
    retention_sec = get_int("JOB_RETENTION_SEC", 86400)
    tombstone_retention_sec = get_int("JOB_TOMBSTONE_RETENTION_SEC", retention_sec)
    if backend == "memory":
        return MemoryJobStore(retention_sec=retention_sec, tombstone_retention_sec=tombstone_retention_sec)

    redis_settings = get_redis_connection_settings()
    prefix = get_str("REDIS_PREFIX", "pms").strip() or "pms"

    if not _HAS_REDIS:
        raise RuntimeError("Redis backend selected but 'redis' package is not installed")

    redis_module = cast(Any, redis_lib)
    redis_cls = redis_module.Redis
    redis_client = redis_cls.from_url(redis_settings.url)
    return RedisJobStore(
        redis_client,
        prefix=prefix,
        retention_sec=retention_sec,
        tombstone_retention_sec=tombstone_retention_sec,
    )


@lru_cache(maxsize=1)
def get_job_store() -> JobStore:
    return create_job_store()


def now_ms() -> int:
    return int(time.time() * 1000)


def _clear_job_store_cache() -> None:
    get_job_store.cache_clear()
