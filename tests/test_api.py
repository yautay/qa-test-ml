from __future__ import annotations

import base64

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


def test_compare_invalid_lpips_net_returns_422(client: TestClient):
    r = client.post(
        "/compare",
        json={
            "ref_path": "tests/assets/ref_1.png",
            "test_path": "tests/assets/test_1.png",
            "config": {"lpips_net": "nope"},
        },
    )
    assert r.status_code == 422


def test_compare_returns_lpips_dists_and_heatmap(
    monkeypatch: pytest.MonkeyPatch, client: TestClient
):
    import app.api.routes.compare as compare_routes
    from app.metrics.base import Metric, MetricResult

    class DummyLpips(Metric):
        name = "lpips"

        def distance(self, ref_path: str, test_path: str, config) -> MetricResult:
            return MetricResult(value=0.123, meta={"metric": "lpips"})

        def heatmap_png(self, ref_path: str, test_path: str, config) -> bytes:
            return b"\x89PNG\r\n\x1a\nFAKE"

    class DummyDists(Metric):
        name = "dists"

        def distance(self, ref_path: str, test_path: str, config) -> MetricResult:
            return MetricResult(value=0.456, meta={"metric": "dists"})

    lpips = DummyLpips()
    dists = DummyDists()

    def _get(name: str):
        if name == "lpips":
            return lpips
        if name == "dists":
            return dists
        raise KeyError(name)

    monkeypatch.setattr(compare_routes.registry, "get", _get)

    r = client.post(
        "/compare",
        json={
            "ref_path": "tests/assets/ref_1.png",
            "test_path": "tests/assets/test_1.png",
            "config": {"lpips_net": "vgg", "force_device": "cpu"},
        },
    )

    assert r.status_code == 200
    body = r.json()
    assert body["lpips"]["value"] == 0.123
    assert body["dists"]["value"] == 0.456
    assert base64.b64decode(body["lpips_heatmap_png_base64"]).startswith(b"\x89PNG")


def test_compare_lpips_returns_score_and_heatmap(
    monkeypatch: pytest.MonkeyPatch, client: TestClient
):
    import app.api.routes.compare as compare_routes
    from app.metrics.base import Metric, MetricResult

    class DummyLpips(Metric):
        name = "lpips"

        def distance(self, ref_path: str, test_path: str, config) -> MetricResult:
            return MetricResult(value=0.321, meta={"metric": "lpips", "device": "cpu"})

        def heatmap_png(self, ref_path: str, test_path: str, config) -> bytes:
            return b"\x89PNG\r\n\x1a\nFAKE"

    monkeypatch.setattr(compare_routes.registry, "get", lambda name: DummyLpips())

    r = client.post(
        "/compare/lpips",
        json={
            "ref_path": "tests/assets/ref_1.png",
            "test_path": "tests/assets/test_1.png",
            "config": {"net": "vgg", "force_device": "cpu"},
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["lpips"]["value"] == 0.321
    assert base64.b64decode(body["lpips_heatmap_png_base64"]).startswith(b"\x89PNG")


def test_compare_dists_returns_only_score(monkeypatch: pytest.MonkeyPatch, client: TestClient):
    import app.api.routes.compare as compare_routes
    from app.metrics.base import Metric, MetricResult

    class DummyDists(Metric):
        name = "dists"

        def distance(self, ref_path: str, test_path: str, config) -> MetricResult:
            assert config.force_device == "cpu"
            return MetricResult(value=0.456, meta={"metric": "dists", "device": "cpu"})

    monkeypatch.setattr(compare_routes.registry, "get", lambda name: DummyDists())

    r = client.post(
        "/compare/dists",
        json={
            "ref_path": "tests/assets/ref_1.png",
            "test_path": "tests/assets/test_1.png",
            "config": {"force_device": "cpu"},
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert set(body.keys()) == {"dists"}
    assert body["dists"]["value"] == 0.456


def test_compare_lpips_maps_file_not_found_to_404(
    monkeypatch: pytest.MonkeyPatch, client: TestClient
):
    import app.api.routes.compare as compare_routes
    from app.metrics.base import Metric

    class DummyLpips(Metric):
        name = "lpips"

        def distance(self, ref_path: str, test_path: str, config):
            raise FileNotFoundError("missing.png")

    monkeypatch.setattr(compare_routes.registry, "get", lambda name: DummyLpips())

    r = client.post(
        "/compare/lpips",
        json={
            "ref_path": "tests/assets/ref_1.png",
            "test_path": "tests/assets/test_1.png",
            "config": {"net": "vgg"},
        },
    )
    assert r.status_code == 404


def test_compare_dists_maps_value_error_to_400(monkeypatch: pytest.MonkeyPatch, client: TestClient):
    import app.api.routes.compare as compare_routes
    from app.metrics.base import Metric

    class DummyDists(Metric):
        name = "dists"

        def distance(self, ref_path: str, test_path: str, config):
            raise ValueError("CUDA requested but not available on this host")

    monkeypatch.setattr(compare_routes.registry, "get", lambda name: DummyDists())

    r = client.post(
        "/compare/dists",
        json={
            "ref_path": "tests/assets/ref_1.png",
            "test_path": "tests/assets/test_1.png",
            "config": {"force_device": "cuda"},
        },
    )
    assert r.status_code == 400


def test_compare_returns_generic_500_when_api_debug_disabled(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("API_DEBUG", "0")
    import app.api.routes.compare as compare_routes
    from app.main import create_app
    from app.metrics.base import Metric

    class BoomMetric(Metric):
        name = "dists"

        def distance(self, ref_path: str, test_path: str, config):
            raise RuntimeError("sensitive internal message")

    monkeypatch.setattr(compare_routes.registry, "get", lambda name: BoomMetric())

    client = TestClient(create_app(), raise_server_exceptions=False)
    r = client.post(
        "/compare/dists",
        json={
            "ref_path": "tests/assets/ref_1.png",
            "test_path": "tests/assets/test_1.png",
            "config": {"force_device": "cpu"},
        },
    )
    assert r.status_code == 500
    assert "sensitive internal message" not in r.text
