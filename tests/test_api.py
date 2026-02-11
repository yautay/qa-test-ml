from __future__ import annotations
import pytest
import torch
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
            "ref_path": "tests/assets/ref_1.png",
            "test_path": "tests/assets/test_1.png",
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
            "ref_path": "tests/assets/ref_1.png",
            "test_path": "tests/assets/test_1.png",
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
            "ref_path": "tests/assets/ref_1.png",
            "test_path": "tests/assets/test_1.png",
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
            "ref_path": "tests/assets/ref_1.png",
            "test_path": "tests/assets/test_1.png",
            "config": {"metric": "dists"},
        },
    )
    assert r.status_code == 400


def test_compare_supports_dists(monkeypatch: pytest.MonkeyPatch, client: TestClient):
    from app.metrics.base import Metric, MetricResult
    import app.api.routes.compare as compare_routes

    class DummyDists(Metric):
        name = "dists"

        def distance(self, ref_path: str, test_path: str, config) -> MetricResult:
            assert getattr(config, "metric") == "dists"
            assert getattr(config, "force_device") == "cpu"
            return MetricResult(value=0.456, meta={"metric": self.name, "device": "cpu"})

    monkeypatch.setattr(compare_routes.registry, "get", lambda name: DummyDists())

    r = client.post(
        "/compare",
        json={
            "ref_path": "tests/assets/ref_1.png",
            "test_path": "tests/assets/test_1.png",
            "config": {"metric": "dists", "force_device": "cpu"},
        },
    )
    assert r.status_code == 200
    assert r.json()["value"] == 0.456


def test_compare_blocks_path_outside_image_base_dir(client: TestClient):
    r = client.post(
        "/compare",
        json={
            "ref_path": "/etc/passwd",
            "test_path": "tests/assets/test_1.png",
            "config": {"metric": "lpips", "net": "vgg", "force_device": "cpu"},
        },
    )
    assert r.status_code == 403


def test_compare_returns_generic_500_when_api_debug_disabled(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("API_DEBUG", "0")
    from app.main import create_app
    import app.api.routes.compare as compare_routes
    from app.metrics.base import Metric

    class BoomMetric(Metric):
        name = "lpips"

        def distance(self, ref_path: str, test_path: str, config):
            raise RuntimeError("sensitive internal message")

    monkeypatch.setattr(compare_routes.registry, "get", lambda name: BoomMetric())

    client = TestClient(create_app(), raise_server_exceptions=False)
    r = client.post(
        "/compare",
        json={
            "ref_path": "tests/assets/ref_1.png",
            "test_path": "tests/assets/test_1.png",
            "config": {"metric": "lpips", "net": "vgg", "force_device": "cpu"},
        },
    )
    assert r.status_code == 500
    assert "sensitive internal message" not in r.text


def test_compare_rejects_cuda_when_unavailable(client: TestClient):
    if torch.cuda.is_available():
        pytest.skip("Host has CUDA; this test expects no CUDA")

    r = client.post(
        "/compare",
        json={
            "ref_path": "tests/assets/ref_1.png",
            "test_path": "tests/assets/test_1.png",
            "config": {"metric": "lpips", "net": "vgg", "force_device": "cuda"},
        },
    )
    assert r.status_code == 400
