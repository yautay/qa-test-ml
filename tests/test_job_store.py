from __future__ import annotations

import json

import pytest

from app.core.job_store import RedisJobStore, get_redis_startup_check_mode, validate_redis_job_store_startup


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
        job_ttl_sec=60,
        heatmap_ttl_sec=60,
    )

    jobs = store.list_jobs()

    assert len(jobs) == 1
    assert jobs[0].job_id == "job-1"
    assert redis_client.zrem_calls == [("pms-test:jobs:index", ("job-2",))]


def test_validate_redis_job_store_startup_accepts_successful_ping():
    store = RedisJobStore(
        _StartupRedis(ping_result=True),
        prefix="pms-test",
        job_ttl_sec=60,
        heatmap_ttl_sec=60,
    )

    validate_redis_job_store_startup(store)


def test_validate_redis_job_store_startup_rejects_unavailable_ping():
    store = RedisJobStore(
        _StartupRedis(ping_result=False),
        prefix="pms-test",
        job_ttl_sec=60,
        heatmap_ttl_sec=60,
    )

    with pytest.raises(RuntimeError, match="ping returned unavailable"):
        validate_redis_job_store_startup(store)


def test_validate_redis_job_store_startup_rejects_ping_exception():
    store = RedisJobStore(
        _StartupRedis(ping_error=ConnectionError("redis offline")),
        prefix="pms-test",
        job_ttl_sec=60,
        heatmap_ttl_sec=60,
    )

    with pytest.raises(RuntimeError, match="ping raised an exception"):
        validate_redis_job_store_startup(store)


def test_validate_redis_job_store_startup_accepts_rw_mode_without_ping_permission():
    store = RedisJobStore(
        _StartupRedis(ping_error=PermissionError("ping denied")),
        prefix="pms-test",
        job_ttl_sec=60,
        heatmap_ttl_sec=60,
    )

    store.validate_startup(mode="rw")


def test_validate_redis_job_store_startup_rejects_rw_probe_exception():
    store = RedisJobStore(
        _StartupRedis(set_error=PermissionError("set denied")),
        prefix="pms-test",
        job_ttl_sec=60,
        heatmap_ttl_sec=60,
    )

    with pytest.raises(RuntimeError, match="rw check raised an exception"):
        store.validate_startup(mode="rw")


def test_validate_redis_job_store_startup_rejects_rw_probe_mismatch():
    store = RedisJobStore(
        _StartupRedis(get_value="wrong-value"),
        prefix="pms-test",
        job_ttl_sec=60,
        heatmap_ttl_sec=60,
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
        job_ttl_sec=60,
        heatmap_ttl_sec=60,
    )

    assert store.is_available() is True


def test_redis_is_available_returns_false_for_rw_probe_failure(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("REDIS_STARTUP_CHECK_MODE", "rw")
    store = RedisJobStore(
        _StartupRedis(set_error=PermissionError("set denied")),
        prefix="pms-test",
        job_ttl_sec=60,
        heatmap_ttl_sec=60,
    )

    assert store.is_available() is False
