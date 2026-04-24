from __future__ import annotations

import os
import time
import uuid
from collections.abc import Iterator
from pathlib import Path
from urllib.parse import SplitResult, quote, unquote, urlsplit, urlunsplit

import pytest
from fastapi.testclient import TestClient

from app.core import celery_app as celery_app_module
from app.core import config as app_config
from app.core import hmac_auth as hmac_auth_module
from app.core import job_store as job_store_module
from app.main import create_app

pytestmark = pytest.mark.redis_integration


def _clear_runtime_caches() -> None:
    app_config._clear_config_cache()
    hmac_auth_module._clear_nonce_cache()
    job_store_module._clear_job_store_cache()
    celery_app_module._clear_celery_app_cache()


def _asset_bytes(filename: str) -> bytes:
    path = Path(__file__).parent / "assets" / filename
    return path.read_bytes()


def _install_dummy_metrics(monkeypatch: pytest.MonkeyPatch) -> None:
    import app.tasks.compare_tasks as tasks_module
    from app.metrics.base import Metric, MetricResult

    class DummyLpips(Metric):
        name = "lpips"

        def distance(self, ref_path: str, test_path: str, config) -> MetricResult:
            return MetricResult(value=0.11, meta={"metric": "lpips"})

        def heatmap_png(self, ref_path: str, test_path: str, config) -> bytes:
            return b"\x89PNG\r\n\x1a\nFAKE"

    class DummyDists(Metric):
        name = "dists"

        def distance(self, ref_path: str, test_path: str, config) -> MetricResult:
            return MetricResult(value=0.22, meta={"metric": "dists"})

    lpips = DummyLpips()
    dists = DummyDists()

    def _get(name: str):
        if name == "lpips":
            return lpips
        if name == "dists":
            return dists
        raise KeyError(name)

    monkeypatch.setattr(tasks_module.registry, "get", _get)


def _wait_terminal(client: TestClient, job_id: str) -> dict[str, object]:
    for _ in range(80):
        response = client.get(f"/v1/compare/jobs/{job_id}")
        assert response.status_code == 200
        body = response.json()
        if body["status"] in {"done", "error"}:
            return body
        time.sleep(0.05)
    raise AssertionError("job did not finish in time")


def _redis_url_parts(redis_url: str) -> SplitResult:
    parts = urlsplit(redis_url)
    if not parts.scheme or not parts.hostname:
        raise RuntimeError("PMS_REDIS_AUTH_URL must include scheme and host")
    return parts


def _replace_password(redis_url: str, replacement: str) -> str:
    parts = _redis_url_parts(redis_url)
    username = unquote(parts.username) if parts.username is not None else ""
    host = parts.hostname or ""
    netloc = host
    if parts.port is not None:
        netloc = f"{netloc}:{parts.port}"

    auth = ""
    if username:
        auth = f"{quote(username, safe='')}:{quote(replacement, safe='')}@"
    elif parts.password is not None:
        auth = f":{quote(replacement, safe='')}@"
    return urlunsplit((parts.scheme, f"{auth}{netloc}", parts.path, parts.query, parts.fragment))


def _live_redis_available(redis_url: str) -> bool:
    redis_module = job_store_module.redis_lib
    if redis_module is None:
        return False

    try:
        client = redis_module.Redis.from_url(redis_url, socket_connect_timeout=1, socket_timeout=1)
        return bool(client.ping())
    except Exception:
        return False


@pytest.fixture()
def redis_auth_url(monkeypatch: pytest.MonkeyPatch) -> Iterator[str]:
    if os.getenv("RUN_REDIS_INTEGRATION", "").strip().lower() not in {"1", "true", "yes"}:
        pytest.skip("Set RUN_REDIS_INTEGRATION=1 to run live Redis auth integration tests")

    redis_url = os.getenv("PMS_REDIS_AUTH_URL", "").strip()
    if not redis_url:
        pytest.skip("Set PMS_REDIS_AUTH_URL to an auth-enabled local Redis URL")
    if not _live_redis_available(redis_url):
        pytest.skip("Live auth-enabled Redis is unavailable for PMS_REDIS_AUTH_URL")

    monkeypatch.setenv("JOB_STORE_BACKEND", "redis")
    monkeypatch.setenv("CELERY_TASK_ALWAYS_EAGER", "true")
    monkeypatch.setenv("CELERY_TASK_EAGER_PROPAGATES", "false")
    monkeypatch.setenv("HMAC_ENABLED", "false")

    _clear_runtime_caches()
    yield redis_url
    _clear_runtime_caches()


@pytest.mark.redis_integration
def test_redis_auth_url_mode_full_flow(monkeypatch: pytest.MonkeyPatch, redis_auth_url: str):
    _install_dummy_metrics(monkeypatch)
    monkeypatch.setenv("REDIS_URL", redis_auth_url)
    monkeypatch.setenv("REDIS_PREFIX", f"pms-it-url-{uuid.uuid4().hex[:8]}")
    _clear_runtime_caches()

    job_id = str(uuid.uuid4())

    with TestClient(create_app()) as client:
        health = client.get("/health")
        assert health.status_code == 200
        assert health.json()["job_store"] == {"backend": "redis", "available": True}

        create_response = client.post(
            "/v1/compare/jobs",
            data={
                "job_id": job_id,
                "pair_id": "pair_redis_url",
                "metric": "both",
                "model": "alex",
                "normalize": "true",
            },
            files={
                "img_a": ("a.png", _asset_bytes("ref_1.png"), "image/png"),
                "img_b": ("b.png", _asset_bytes("test_1.png"), "image/png"),
            },
        )
        assert create_response.status_code == 202

        status_body = _wait_terminal(client, job_id)
        assert status_body["status"] == "done"

    with TestClient(create_app()) as second_client:
        readback = second_client.get(f"/v1/compare/jobs/{job_id}")
        assert readback.status_code == 200
        assert readback.json()["status"] == "done"


@pytest.mark.redis_integration
def test_redis_auth_split_vars_mode_full_flow(monkeypatch: pytest.MonkeyPatch, redis_auth_url: str):
    _install_dummy_metrics(monkeypatch)
    parts = _redis_url_parts(redis_auth_url)

    db = parts.path.removeprefix("/") if parts.path else "0"
    if not db:
        db = "0"

    monkeypatch.setenv("REDIS_URL", "")
    monkeypatch.setenv("REDIS_HOST", parts.hostname or "127.0.0.1")
    monkeypatch.setenv("REDIS_PORT", str(parts.port or 6379))
    monkeypatch.setenv("REDIS_DB", db)
    monkeypatch.setenv("REDIS_USERNAME", unquote(parts.username) if parts.username is not None else "")
    monkeypatch.setenv("REDIS_PASSWORD", unquote(parts.password) if parts.password is not None else "")
    monkeypatch.setenv("REDIS_TLS", "true" if parts.scheme == "rediss" else "false")
    monkeypatch.setenv("REDIS_PREFIX", f"pms-it-split-{uuid.uuid4().hex[:8]}")
    _clear_runtime_caches()

    job_id = str(uuid.uuid4())

    with TestClient(create_app()) as client:
        health = client.get("/health")
        assert health.status_code == 200
        assert health.json()["job_store"] == {"backend": "redis", "available": True}

        create_response = client.post(
            "/v1/compare/jobs",
            data={
                "job_id": job_id,
                "pair_id": "pair_redis_split",
                "metric": "lpips",
                "model": "alex",
                "normalize": "false",
            },
            files={
                "img_a": ("a.png", _asset_bytes("ref_1.png"), "image/png"),
                "img_b": ("b.png", _asset_bytes("test_1.png"), "image/png"),
            },
        )
        assert create_response.status_code == 202

        status_body = _wait_terminal(client, job_id)
        assert status_body["status"] == "done"

    with TestClient(create_app()) as second_client:
        readback = second_client.get(f"/v1/compare/jobs/{job_id}")
        assert readback.status_code == 200
        assert readback.json()["status"] == "done"


@pytest.mark.redis_integration
def test_redis_auth_invalid_credentials_fail_fast_without_secret_leak(
    monkeypatch: pytest.MonkeyPatch,
    redis_auth_url: str,
    capsys: pytest.CaptureFixture[str],
):
    parts = _redis_url_parts(redis_auth_url)
    if parts.password is None or parts.password == "":
        pytest.skip("PMS_REDIS_AUTH_URL must include password for invalid-credentials scenario")

    raw_password = unquote(parts.password)
    invalid_url = _replace_password(redis_auth_url, f"{raw_password}-invalid")

    monkeypatch.setenv("REDIS_URL", invalid_url)
    monkeypatch.setenv("REDIS_PREFIX", f"pms-it-invalid-{uuid.uuid4().hex[:8]}")
    _clear_runtime_caches()

    with pytest.raises(RuntimeError, match="startup validation failed") as exc_info, TestClient(create_app()):
        pass

    assert raw_password not in str(exc_info.value)
    captured = capsys.readouterr()
    assert raw_password not in captured.err
    assert raw_password not in captured.out
