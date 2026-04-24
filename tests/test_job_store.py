from __future__ import annotations

import json

import pytest

from app.core import metrics as app_metrics
from app.core.job_store import (
    JobState,
    MemoryJobStore,
    RedisJobStore,
    get_redis_startup_check_mode,
    validate_redis_job_store_startup,
)


def _job(job_id: str, *, created_at_ms: int = 1000) -> JobState:
    return JobState(
        job_id=job_id,
        pair_id="pair-1",
        metric="lpips",
        model="alex",
        normalize=True,
        img_a_name="a.png",
        img_b_name="b.png",
        status="queued",
        created_at_ms=created_at_ms,
    )


class _FakeRedis:
    def __init__(self):
        self.zrem_calls: list[tuple[str, tuple[str, ...]]] = []

    def zrange(self, key: str, start: int, end: int):
        return [b"job-1", b"job-2"]

    def mget(self, keys: list[str]):
        payload = json.dumps(
            {
                "job_id": "job-1",
                "pair_id": "pair-1",
                "metric": "lpips",
                "model": "alex",
                "normalize": True,
                "img_a_name": "a.png",
                "img_b_name": "b.png",
                "status": "done",
                "has_heatmap": False,
                "created_at_ms": 123,
            }
        )
        return [payload, None]

    def zrem(self, key: str, *members: str):
        self.zrem_calls.append((key, members))
        return 1


class _StartupRedis:
    def __init__(
        self,
        *,
        ping_result: bool = True,
        ping_error: Exception | None = None,
        set_error: Exception | None = None,
        get_error: Exception | None = None,
        set_result: bool = True,
        get_value: str | bytes | None = None,
    ):
        self._ping_result = ping_result
        self._ping_error = ping_error
        self._set_error = set_error
        self._get_error = get_error
        self._set_result = set_result
        self._get_value = get_value
        self._values: dict[str, str] = {}

    def ping(self) -> bool:
        if self._ping_error is not None:
            raise self._ping_error
        return self._ping_result

    def set(self, key: str, value: str, ex: int | None = None) -> bool:
        del ex
        if self._set_error is not None:
            raise self._set_error
        self._values[key] = value
        return self._set_result

    def get(self, key: str) -> str | bytes | None:
        if self._get_error is not None:
            raise self._get_error
        if self._get_value is not None:
            return self._get_value
        return self._values.get(key)

    def delete(self, key: str) -> int:
        self._values.pop(key, None)
        return 1


def test_redis_list_jobs_prunes_stale_index_entries():
    redis_client = _FakeRedis()
    store = RedisJobStore(
        redis_client,
        prefix="pms-test",
        retention_sec=60,
    )
    before = app_metrics.retention_cleanup_total.labels(
        backend="redis",
        artifact="jobs_index",
        outcome="pruned",
    )._value.get()

    jobs = store.list_jobs()

    assert len(jobs) == 1
    assert jobs[0].job_id == "job-1"
    assert redis_client.zrem_calls == [("pms-test:jobs:index", ("job-2",))]
    after = app_metrics.retention_cleanup_total.labels(
        backend="redis",
        artifact="jobs_index",
        outcome="pruned",
    )._value.get()
    assert after - before == 1


def test_validate_redis_job_store_startup_accepts_successful_ping():
    store = RedisJobStore(
        _StartupRedis(ping_result=True),
        prefix="pms-test",
        retention_sec=60,
    )

    validate_redis_job_store_startup(store)


def test_validate_redis_job_store_startup_rejects_unavailable_ping():
    store = RedisJobStore(
        _StartupRedis(ping_result=False),
        prefix="pms-test",
        retention_sec=60,
    )

    with pytest.raises(RuntimeError, match="ping returned unavailable"):
        validate_redis_job_store_startup(store)


def test_validate_redis_job_store_startup_rejects_ping_exception():
    store = RedisJobStore(
        _StartupRedis(ping_error=ConnectionError("redis offline")),
        prefix="pms-test",
        retention_sec=60,
    )

    with pytest.raises(RuntimeError, match="ping raised an exception"):
        validate_redis_job_store_startup(store)


def test_validate_redis_job_store_startup_accepts_rw_mode_without_ping_permission():
    store = RedisJobStore(
        _StartupRedis(ping_error=PermissionError("ping denied")),
        prefix="pms-test",
        retention_sec=60,
    )

    store.validate_startup(mode="rw")


def test_validate_redis_job_store_startup_rejects_rw_probe_exception():
    store = RedisJobStore(
        _StartupRedis(set_error=PermissionError("set denied")),
        prefix="pms-test",
        retention_sec=60,
    )

    with pytest.raises(RuntimeError, match="rw check raised an exception"):
        store.validate_startup(mode="rw")


def test_validate_redis_job_store_startup_rejects_rw_probe_mismatch():
    store = RedisJobStore(
        _StartupRedis(get_value="wrong-value"),
        prefix="pms-test",
        retention_sec=60,
    )

    with pytest.raises(RuntimeError, match="rw probe value mismatch"):
        store.validate_startup(mode="rw")


def test_get_redis_startup_check_mode_defaults_to_ping(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("REDIS_STARTUP_CHECK_MODE", raising=False)

    assert get_redis_startup_check_mode() == "ping"


def test_get_redis_startup_check_mode_accepts_rw(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("REDIS_STARTUP_CHECK_MODE", "rw")

    assert get_redis_startup_check_mode() == "rw"


def test_get_redis_startup_check_mode_rejects_invalid_value(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("REDIS_STARTUP_CHECK_MODE", "invalid")

    with pytest.raises(RuntimeError, match="must be one of"):
        get_redis_startup_check_mode()


def test_redis_is_available_uses_rw_mode_without_ping_permission(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("REDIS_STARTUP_CHECK_MODE", "rw")
    store = RedisJobStore(
        _StartupRedis(ping_error=PermissionError("ping denied")),
        prefix="pms-test",
        retention_sec=60,
    )

    assert store.is_available() is True


def test_redis_is_available_returns_false_for_rw_probe_failure(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("REDIS_STARTUP_CHECK_MODE", "rw")
    store = RedisJobStore(
        _StartupRedis(set_error=PermissionError("set denied")),
        prefix="pms-test",
        retention_sec=60,
    )

    assert store.is_available() is False


def test_memory_store_retention_prunes_job_heatmap_and_sets_tombstone(monkeypatch: pytest.MonkeyPatch):
    clock = {"now": 1_000}

    monkeypatch.setattr("app.core.job_store.now_ms", lambda: clock["now"])
    store = MemoryJobStore(retention_sec=1, tombstone_retention_sec=3)
    job_cleanup_before = app_metrics.retention_cleanup_total.labels(
        backend="memory",
        artifact="job_state",
        outcome="expired",
    )._value.get()
    heatmap_cleanup_before = app_metrics.retention_cleanup_total.labels(
        backend="memory",
        artifact="heatmap",
        outcome="expired",
    )._value.get()
    store.create_job(_job("job-1", created_at_ms=1_000))
    store.set_heatmap("job-1", b"png")

    assert store.get_job("job-1") is not None
    assert store.get_heatmap("job-1") == b"png"
    assert store.is_job_expired("job-1") is False

    clock["now"] = 2_500

    assert store.get_job("job-1") is None
    assert store.get_heatmap("job-1") is None
    assert store.is_job_expired("job-1") is True
    assert store.list_jobs() == []
    job_cleanup_after = app_metrics.retention_cleanup_total.labels(
        backend="memory",
        artifact="job_state",
        outcome="expired",
    )._value.get()
    heatmap_cleanup_after = app_metrics.retention_cleanup_total.labels(
        backend="memory",
        artifact="heatmap",
        outcome="expired",
    )._value.get()
    assert job_cleanup_after - job_cleanup_before == 1
    assert heatmap_cleanup_after - heatmap_cleanup_before == 1


def test_memory_store_prunes_tombstones_lazily(monkeypatch: pytest.MonkeyPatch):
    clock = {"now": 1_000}

    monkeypatch.setattr("app.core.job_store.now_ms", lambda: clock["now"])
    store = MemoryJobStore(retention_sec=1, tombstone_retention_sec=1)
    store.create_job(_job("job-1", created_at_ms=1_000))

    clock["now"] = 2_500
    assert store.get_job("job-1") is None
    assert store.is_job_expired("job-1") is True

    clock["now"] = 3_600
    assert store.is_job_expired("job-1") is False


class _RetentionRedis:
    def __init__(self):
        self._now = 0
        self._kv: dict[str, bytes] = {}
        self._expiry: dict[str, int] = {}

    def _purge_if_expired(self, key: str) -> None:
        expires_at = self._expiry.get(key)
        if expires_at is not None and self._now >= expires_at:
            self._kv.pop(key, None)
            self._expiry.pop(key, None)

    def set(self, key: str, value: str | bytes, *, nx: bool = False, ex: int | None = None):
        self._purge_if_expired(key)
        if nx and key in self._kv:
            return False
        payload = value if isinstance(value, bytes) else value.encode("utf-8")
        self._kv[key] = payload
        if ex is None:
            self._expiry.pop(key, None)
        else:
            self._expiry[key] = self._now + ex
        return True

    def get(self, key: str):
        self._purge_if_expired(key)
        return self._kv.get(key)

    def exists(self, key: str) -> int:
        self._purge_if_expired(key)
        return 1 if key in self._kv else 0

    def ttl(self, key: str) -> int:
        self._purge_if_expired(key)
        if key not in self._kv:
            return -2
        expires_at = self._expiry.get(key)
        if expires_at is None:
            return -1
        remaining = expires_at - self._now
        return remaining if remaining > 0 else -2

    def zadd(self, key: str, mapping: dict[str, float]):
        del key, mapping
        return 1


def test_redis_store_tombstone_survives_job_expiry_window():
    redis_client = _RetentionRedis()
    store = RedisJobStore(redis_client, prefix="pms-test", retention_sec=2, tombstone_retention_sec=4)
    store.create_job(_job("job-1", created_at_ms=123))

    redis_client._now = 1
    assert store.get_job("job-1") is not None
    assert store.is_job_expired("job-1") is False

    redis_client._now = 3
    assert store.get_job("job-1") is None
    assert store.is_job_expired("job-1") is True

    redis_client._now = 7
    assert store.is_job_expired("job-1") is False
