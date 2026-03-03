from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.core import config as app_config
from app.core import job_store as job_store_module


@pytest.fixture(autouse=True)
def _runtime(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("JOB_STORE_BACKEND", "memory")
    app_config._clear_config_cache()
    job_store_module._clear_job_store_cache()
    yield
    app_config._clear_config_cache()
    job_store_module._clear_job_store_cache()


def test_contract_health_response_shape():
    from app.main import create_app

    client = TestClient(create_app())

    r = client.get("/health")

    assert r.status_code == 200
    data = r.json()
    assert set(data.keys()) == {"status", "metrics", "job_store", "git", "gpu"}
    assert data["status"] == "ok"
    assert isinstance(data["metrics"], list)
    assert set(data["job_store"].keys()) == {"backend", "available"}
    assert set(data["git"].keys()) == {"branch", "tag", "last_commit", "committer", "date"}
    assert set(data["gpu"].keys()) == {"enabled", "mode", "available", "fallback_to_cpu"}
