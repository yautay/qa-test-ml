from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client() -> TestClient:
    from app.main import app

    return TestClient(app)


def test_health(client: TestClient):
    r = client.get("/health")
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "ok"
    assert data["device"] in ("cpu", "cuda")
    assert "lpips" in data["metrics"]
    assert "dists" in data["metrics"]
    assert set(data["git"].keys()) == {"branch", "tag", "last_commit", "committer", "date"}
    assert all(isinstance(value, str) for value in data["git"].values())


def test_legacy_compare_endpoint_removed(client: TestClient):
    r = client.post(
        "/compare",
        json={
            "ref_path": "tests/assets/ref_1.png",
            "test_path": "tests/assets/test_1.png",
            "config": {},
        },
    )
    assert r.status_code == 404
