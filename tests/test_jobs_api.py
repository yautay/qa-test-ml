from __future__ import annotations

import time
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client() -> TestClient:
    from app.main import create_app

    return TestClient(create_app())


def _install_dummy_metrics(monkeypatch: pytest.MonkeyPatch):
    import app.core.jobs as jobs_module
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

    monkeypatch.setattr(jobs_module.registry, "get", _get)


def _install_failing_metrics(monkeypatch: pytest.MonkeyPatch):
    import app.core.jobs as jobs_module
    from app.metrics.base import Metric

    class FailingLpips(Metric):
        name = "lpips"

        def distance(self, ref_path: str, test_path: str, config):
            raise RuntimeError("LPIPS backend failure")

        def heatmap_png(self, ref_path: str, test_path: str, config) -> bytes:
            return b""

    class DummyDists(Metric):
        name = "dists"

        def distance(self, ref_path: str, test_path: str, config):
            raise AssertionError("dists should not be called for lpips metric")

    lpips = FailingLpips()
    dists = DummyDists()

    def _get(name: str):
        if name == "lpips":
            return lpips
        if name == "dists":
            return dists
        raise KeyError(name)

    monkeypatch.setattr(jobs_module.registry, "get", _get)


def _wait_done(client: TestClient, job_id: str) -> dict:
    for _ in range(40):
        r = client.get(f"/v1/compare/jobs/{job_id}")
        assert r.status_code == 200
        body = r.json()
        if body["status"] in {"done", "error"}:
            return body
        time.sleep(0.05)
    raise AssertionError("job did not finish in time")


def _asset_bytes(filename: str) -> bytes:
    path = Path(__file__).parent / "assets" / filename
    return path.read_bytes()


def test_create_job_and_poll_done(monkeypatch: pytest.MonkeyPatch, client: TestClient):
    _install_dummy_metrics(monkeypatch)
    job_id = str(uuid.uuid4())

    r = client.post(
        "/v1/compare/jobs",
        data={
            "job_id": job_id,
            "pair_id": "pair_1",
            "metric": "both",
            "model": "alex",
            "normalize": "true",
        },
        files={
            "img_a": ("a.png", _asset_bytes("ref_1.png"), "image/png"),
            "img_b": ("b.png", _asset_bytes("test_1.png"), "image/png"),
        },
    )

    assert r.status_code == 202
    body = r.json()
    assert body["job_id"] == job_id
    assert body["status"] == "queued"
    assert body["poll_url"].endswith(f"/v1/compare/jobs/{job_id}")

    status_body = _wait_done(client, job_id)
    assert status_body["status"] == "done"
    assert status_body["lpips"] == 0.11
    assert status_body["dists"] == 0.22
    assert isinstance(status_body["timing_ms"], int)
    assert status_body["heatmap_url"].endswith(f"/v1/compare/jobs/{job_id}/heatmap")


def test_jobs_list_and_heatmap_download(monkeypatch: pytest.MonkeyPatch, client: TestClient):
    _install_dummy_metrics(monkeypatch)
    job_id = str(uuid.uuid4())

    create_resp = client.post(
        "/v1/compare/jobs",
        data={
            "job_id": job_id,
            "pair_id": "pair_2",
            "metric": "lpips",
            "model": "alex",
            "normalize": "false",
        },
        files={
            "img_a": ("a.png", _asset_bytes("ref_1.png"), "image/png"),
            "img_b": ("b.png", _asset_bytes("test_1.png"), "image/png"),
        },
    )
    assert create_resp.status_code == 202
    _wait_done(client, job_id)

    list_resp = client.get("/v1/compare/jobs")
    assert list_resp.status_code == 200
    jobs = list_resp.json()["jobs"]
    assert any(job["job_id"] == job_id for job in jobs)

    heatmap_resp = client.get(f"/v1/compare/jobs/{job_id}/heatmap")
    assert heatmap_resp.status_code == 200
    assert heatmap_resp.headers["content-type"].startswith("image/png")
    assert heatmap_resp.content.startswith(b"\x89PNG")


def test_openapi_contains_jobs_paths(client: TestClient):
    resp = client.get("/openapi.json")
    assert resp.status_code == 200
    paths = resp.json()["paths"]
    assert "/v1/compare/jobs" in paths
    assert "/v1/compare/jobs/{job_id}" in paths
    assert "/v1/compare/jobs/{job_id}/heatmap" in paths
    assert "/v1/compare/jobs/{job_id}/error" in paths


def test_error_url_and_error_endpoint_for_failed_job(
    monkeypatch: pytest.MonkeyPatch, client: TestClient
):
    _install_failing_metrics(monkeypatch)
    job_id = str(uuid.uuid4())

    create_resp = client.post(
        "/v1/compare/jobs",
        data={
            "job_id": job_id,
            "pair_id": "pair_fail",
            "metric": "lpips",
            "model": "alex",
            "normalize": "true",
        },
        files={
            "img_a": ("a.png", _asset_bytes("ref_1.png"), "image/png"),
            "img_b": ("b.png", _asset_bytes("test_1.png"), "image/png"),
        },
    )
    assert create_resp.status_code == 202

    status_body = _wait_done(client, job_id)
    assert status_body["status"] == "error"
    assert status_body["error_message"] == "LPIPS backend failure"
    assert status_body["error_url"].endswith(f"/v1/compare/jobs/{job_id}/error")

    error_resp = client.get(f"/v1/compare/jobs/{job_id}/error")
    assert error_resp.status_code == 200
    error_body = error_resp.json()
    assert error_body["job_id"] == job_id
    assert error_body["status"] == "error"
    assert error_body["error_message"] == "LPIPS backend failure"
    assert isinstance(error_body["timing_ms"], int)


def test_error_endpoint_for_non_failed_job(monkeypatch: pytest.MonkeyPatch, client: TestClient):
    _install_dummy_metrics(monkeypatch)
    job_id = str(uuid.uuid4())

    create_resp = client.post(
        "/v1/compare/jobs",
        data={
            "job_id": job_id,
            "pair_id": "pair_ok",
            "metric": "lpips",
            "model": "alex",
            "normalize": "true",
        },
        files={
            "img_a": ("a.png", _asset_bytes("ref_1.png"), "image/png"),
            "img_b": ("b.png", _asset_bytes("test_1.png"), "image/png"),
        },
    )
    assert create_resp.status_code == 202
    status_body = _wait_done(client, job_id)
    assert status_body["status"] == "done"

    error_resp = client.get(f"/v1/compare/jobs/{job_id}/error")
    assert error_resp.status_code == 409


def test_error_endpoint_for_missing_job(client: TestClient):
    missing_job_id = str(uuid.uuid4())
    error_resp = client.get(f"/v1/compare/jobs/{missing_job_id}/error")
    assert error_resp.status_code == 404
