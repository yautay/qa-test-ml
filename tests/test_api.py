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


def test_compare_invalid_metric_returns_422(client: TestClient):
    r = client.post(
        "/compare",
        json={
            "ref_path": "test/ref_1.png",
            "test_path": "test/test_1.png",
            "config": {"metric": "nope"},
        },
    )
    assert r.status_code == 422


def test_compare_uses_registry_metric(monkeypatch: pytest.MonkeyPatch, client: TestClient):
    from app.metrics.base import Metric, MetricResult
    import app.api.routes.compare as compare_routes

    class DummyMetric(Metric):
        name = "lpips"

        def __init__(self):
            self.seen = None

        def distance(self, ref_path: str, test_path: str, config) -> MetricResult:
            self.seen = (ref_path, test_path, config)
            return MetricResult(value=0.123, meta={"metric": self.name})

    dummy = DummyMetric()

    def _get(name: str):
        assert name == "lpips"
        return dummy

    monkeypatch.setattr(compare_routes.registry, "get", _get)

    r = client.post(
        "/compare",
        json={
            "ref_path": "test/ref_1.png",
            "test_path": "test/test_1.png",
            "config": {"metric": "lpips", "net": "vgg", "force_device": "cpu"},
        },
    )
    assert r.status_code == 200
    assert r.json()["value"] == 0.123
    assert dummy.seen is not None


def test_compare_maps_file_not_found_to_404(monkeypatch: pytest.MonkeyPatch, client: TestClient):
    from app.metrics.base import Metric
    import app.api.routes.compare as compare_routes

    class DummyMetric(Metric):
        name = "lpips"

        def distance(self, ref_path: str, test_path: str, config):
            raise FileNotFoundError("missing.png")

    monkeypatch.setattr(compare_routes.registry, "get", lambda name: DummyMetric())

    r = client.post(
        "/compare",
        json={
            "ref_path": "test/ref_1.png",
            "test_path": "test/test_1.png",
            "config": {"metric": "lpips", "net": "vgg"},
        },
    )
    assert r.status_code == 404


def test_heatmap_dists_not_supported_returns_400(monkeypatch: pytest.MonkeyPatch, client: TestClient):
    from app.metrics.base import Metric, MetricResult
    import app.api.routes.compare as compare_routes

    class DummyDists(Metric):
        name = "dists"

        def distance(self, ref_path: str, test_path: str, config) -> MetricResult:
            return MetricResult(value=0.0, meta={"metric": self.name})

    monkeypatch.setattr(compare_routes.registry, "get", lambda name: DummyDists())

    r = client.post(
        "/compare/heatmap",
        json={
            "ref_path": "test/ref_1.png",
            "test_path": "test/test_1.png",
            "config": {"metric": "dists"},
        },
    )
    assert r.status_code == 400


def test_compare_dists_endpoint_builds_config(monkeypatch: pytest.MonkeyPatch, client: TestClient):
    from app.metrics.base import Metric, MetricResult
    import app.api.routes.compare as compare_routes

    class DummyDists(Metric):
        name = "dists"

        def __init__(self):
            self.force_device = None

        def distance(self, ref_path: str, test_path: str, config) -> MetricResult:
            self.force_device = getattr(config, "force_device", "MISSING")
            assert getattr(config, "metric") == "dists"
            return MetricResult(value=0.456, meta={"metric": self.name, "device": "cpu"})

    dummy = DummyDists()
    monkeypatch.setattr(compare_routes.registry, "get", lambda name: dummy)

    r = client.post(
        "/compare/dists",
        json={
            "ref_path": "test/ref_1.png",
            "test_path": "test/test_1.png",
            "force_device": "cpu",
        },
    )
    assert r.status_code == 200
    assert r.json()["value"] == 0.456
    assert dummy.force_device == "cpu"
