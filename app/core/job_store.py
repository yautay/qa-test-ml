from __future__ import annotations

import json
import threading
import time
from collections.abc import Iterable
from dataclasses import dataclass
from functools import lru_cache
from typing import TYPE_CHECKING, Any, cast

from loguru import logger

if TYPE_CHECKING:
    pass

try:
    import redis as redis_lib

    _HAS_REDIS = True
except ImportError:  # pragma: no cover
    redis_lib = None  # type: ignore[assignment]
    _HAS_REDIS = False

from app.core.config import get_int, get_str
from app.schemas.compare import JobMetricName, JobStatusName


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

    def is_available(self) -> bool:
        raise NotImplementedError


class MemoryJobStore(JobStore):
    backend_name = "memory"

    def __init__(self, *, job_ttl_sec: int = 0, heatmap_ttl_sec: int = 0):
        self._jobs: dict[str, JobState] = {}
        self._heatmaps: dict[str, bytes] = {}
        self._heatmap_created_at_ms: dict[str, int] = {}
        self._job_ttl_sec = max(0, job_ttl_sec)
        self._heatmap_ttl_sec = max(0, heatmap_ttl_sec)
        self._lock = threading.Lock()

    def _prune_expired_locked(self) -> None:
        now = now_ms()

        if self._job_ttl_sec > 0:
            ttl_ms = self._job_ttl_sec * 1000
            expired_jobs = [
                job_id
                for job_id, job in self._jobs.items()
                if job.created_at_ms > 0 and (now - job.created_at_ms) >= ttl_ms
            ]
            for job_id in expired_jobs:
                self._jobs.pop(job_id, None)
                self._heatmaps.pop(job_id, None)
                self._heatmap_created_at_ms.pop(job_id, None)

        if self._heatmap_ttl_sec > 0:
            ttl_ms = self._heatmap_ttl_sec * 1000
            expired_heatmaps = [
                job_id
                for job_id, created_at_ms in self._heatmap_created_at_ms.items()
                if created_at_ms > 0 and (now - created_at_ms) >= ttl_ms
            ]
            for job_id in expired_heatmaps:
                self._heatmaps.pop(job_id, None)
                self._heatmap_created_at_ms.pop(job_id, None)
                if job_id in self._jobs:
                    self._jobs[job_id].has_heatmap = False

    def create_job(self, job: JobState) -> None:
        with self._lock:
            self._prune_expired_locked()
            if job.job_id in self._jobs:
                raise ValueError(f"Job already exists: {job.job_id}")
            self._jobs[job.job_id] = job

    def get_job(self, job_id: str) -> JobState | None:
        with self._lock:
            self._prune_expired_locked()
            return self._jobs.get(job_id)

    def list_jobs(self) -> list[JobState]:
        with self._lock:
            self._prune_expired_locked()
            values = list(self._jobs.values())
        return sorted(values, key=lambda item: item.created_at_ms)

    def update_job(self, job_id: str, **fields: object) -> JobState:
        with self._lock:
            self._prune_expired_locked()
            job = self._jobs[job_id]
            for key, value in fields.items():
                setattr(job, key, value)
            return job

    def set_heatmap(self, job_id: str, heatmap_png: bytes) -> None:
        with self._lock:
            self._prune_expired_locked()
            self._heatmaps[job_id] = heatmap_png
            self._heatmap_created_at_ms[job_id] = now_ms()
            if job_id in self._jobs:
                self._jobs[job_id].has_heatmap = True

    def get_heatmap(self, job_id: str) -> bytes | None:
        with self._lock:
            self._prune_expired_locked()
            return self._heatmaps.get(job_id)

    def is_available(self) -> bool:
        return True


class RedisJobStore(JobStore):
    backend_name = "redis"

    def __init__(
        self,
        redis_client: Any,
        *,
        prefix: str,
        job_ttl_sec: int,
        heatmap_ttl_sec: int,
        index_gc_interval_sec: int,
    ):
        self._redis = redis_client
        self._prefix = prefix
        self._job_ttl_sec = max(0, job_ttl_sec)
        self._heatmap_ttl_sec = max(0, heatmap_ttl_sec)
        self._index_gc_interval_sec = max(1, index_gc_interval_sec)
        self._last_index_gc_ms = 0

    def _job_key(self, job_id: str) -> str:
        return f"{self._prefix}:job:{job_id}"

    def _heatmap_key(self, job_id: str) -> str:
        return f"{self._prefix}:job:{job_id}:heatmap"

    def _jobs_index_key(self) -> str:
        return f"{self._prefix}:jobs:index"

    def _maybe_gc_jobs_index(self) -> None:
        if self._job_ttl_sec <= 0:
            return

        now = now_ms()
        if (now - self._last_index_gc_ms) < (self._index_gc_interval_sec * 1000):
            return

        cutoff_ms = now - self._job_ttl_sec * 1000
        index_key = self._jobs_index_key()
        try:
            self._redis.zremrangebyscore(index_key, 0, cutoff_ms)
            self._last_index_gc_ms = now
        except Exception as exc:
            logger.bind(class_name="RedisJobStore", method_name="_maybe_gc_jobs_index").opt(exception=exc).warning(
                "Redis index GC failed"
            )

    def create_job(self, job: JobState) -> None:
        self._maybe_gc_jobs_index()
        key = self._job_key(job.job_id)
        payload = json.dumps(job.to_dict())
        created = self._redis.set(key, payload, nx=True, ex=self._job_ttl_sec or None)
        if not created:
            raise ValueError(f"Job already exists: {job.job_id}")
        self._redis.zadd(self._jobs_index_key(), {job.job_id: float(job.created_at_ms)})

    def _parse_jobs(self, rows: Iterable[bytes | str]) -> list[JobState]:
        out: list[JobState] = []
        for row in rows:
            payload = row.decode("utf-8") if isinstance(row, bytes) else row
            data = json.loads(payload)
            if isinstance(data, dict):
                out.append(JobState.from_dict(data))
        return out

    def get_job(self, job_id: str) -> JobState | None:
        self._maybe_gc_jobs_index()
        row = self._redis.get(self._job_key(job_id))
        if row is None:
            return None
        payload = row.decode("utf-8") if isinstance(row, bytes) else row
        data = json.loads(payload)
        if not isinstance(data, dict):
            return None
        return JobState.from_dict(data)

    def list_jobs(self) -> list[JobState]:
        self._maybe_gc_jobs_index()
        index_key = self._jobs_index_key()
        ids = self._redis.zrange(index_key, 0, -1)
        if not ids:
            return []

        normalized_ids = [job_id.decode("utf-8") if isinstance(job_id, bytes) else str(job_id) for job_id in ids]
        keys = [self._job_key(job_id) for job_id in normalized_ids]
        rows = self._redis.mget(keys)

        stale_ids = [job_id for job_id, row in zip(normalized_ids, rows) if row is None]
        if stale_ids:
            self._redis.zrem(index_key, *stale_ids)

        valid_rows = [row for row in rows if row is not None]
        return self._parse_jobs(valid_rows)

    def update_job(self, job_id: str, **fields: object) -> JobState:
        self._maybe_gc_jobs_index()
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
        ex = ttl if ttl > 0 else (self._job_ttl_sec or None)
        self._redis.set(key, payload, ex=ex)

        updated = self.get_job(job_id)
        if updated is None:
            raise KeyError(job_id)
        return updated

    def set_heatmap(self, job_id: str, heatmap_png: bytes) -> None:
        self._redis.set(self._heatmap_key(job_id), heatmap_png, ex=self._heatmap_ttl_sec or None)
        self.update_job(job_id, has_heatmap=True)

    def get_heatmap(self, job_id: str) -> bytes | None:
        result = self._redis.get(self._heatmap_key(job_id))
        return cast(bytes | None, result)

    def is_available(self) -> bool:
        try:
            return bool(self._redis.ping())
        except Exception as exc:
            logger.bind(class_name="RedisJobStore", method_name="is_available").opt(exception=exc).warning(
                "Redis ping failed"
            )
            return False


def create_job_store() -> JobStore:
    backend = get_str("JOB_STORE_BACKEND", "redis").strip().lower()
    if backend == "memory":
        return MemoryJobStore(
            job_ttl_sec=get_int("JOB_TTL_SEC", 86400),
            heatmap_ttl_sec=get_int("HEATMAP_TTL_SEC", 86400),
        )

    redis_url = get_str("REDIS_URL", "redis://127.0.0.1:6379/0")
    prefix = get_str("REDIS_PREFIX", "pms").strip() or "pms"
    job_ttl_sec = get_int("JOB_TTL_SEC", 86400)
    heatmap_ttl_sec = get_int("HEATMAP_TTL_SEC", 86400)
    index_gc_interval_sec = get_int("JOB_INDEX_GC_INTERVAL_SEC", 300)

    if not _HAS_REDIS:
        raise RuntimeError("Redis backend selected but 'redis' package is not installed")

    redis_module = cast(Any, redis_lib)
    redis_cls = redis_module.Redis
    redis_client = redis_cls.from_url(redis_url)
    return RedisJobStore(
        redis_client,
        prefix=prefix,
        job_ttl_sec=job_ttl_sec,
        heatmap_ttl_sec=heatmap_ttl_sec,
        index_gc_interval_sec=index_gc_interval_sec,
    )


@lru_cache(maxsize=1)
def get_job_store() -> JobStore:
    return create_job_store()


def now_ms() -> int:
    return int(time.time() * 1000)


def _clear_job_store_cache() -> None:
    get_job_store.cache_clear()
