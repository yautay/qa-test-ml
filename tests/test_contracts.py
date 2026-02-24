from __future__ import annotations

from fastapi.testclient import TestClient


def test_contract_health_response_shape():
    from app.main import create_app

    client = TestClient(create_app())

    r = client.get("/health")

    assert r.status_code == 200
    data = r.json()
    assert set(data.keys()) == {"status", "device", "metrics", "git"}
    assert data["status"] == "ok"
    assert data["device"] in ("cpu", "cuda")
    assert isinstance(data["metrics"], list)
    assert set(data["git"].keys()) == {"branch", "tag", "last_commit", "committer", "date"}
