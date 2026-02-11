from __future__ import annotations

from fastapi.testclient import TestClient


def _client_with_debug(debug: bool) -> TestClient:
    import os

    from app.main import create_app

    os.environ["API_DEBUG"] = "1" if debug else "0"
    return TestClient(create_app(), raise_server_exceptions=False)


def test_contract_health_response_shape():
    client = _client_with_debug(debug=True)

    r = client.get("/health")

    assert r.status_code == 200
    data = r.json()
    assert set(data.keys()) == {"status", "device", "metrics"}
    assert data["status"] == "ok"
    assert data["device"] in ("cpu", "cuda")
    assert isinstance(data["metrics"], list)


def test_contract_compare_success_shape(monkeypatch):
    import app.api.routes.compare as compare_routes
    from app.metrics.base import Metric, MetricResult

    class DummyLpips(Metric):
        name = "lpips"

        def distance(self, ref_path: str, test_path: str, config) -> MetricResult:
            return MetricResult(value=0.42, meta={"metric": "lpips", "device": "cpu"})

        def heatmap_png(self, ref_path: str, test_path: str, config) -> bytes:
            return b"\x89PNG\r\n\x1a\n"

    class DummyDists(Metric):
        name = "dists"

        def distance(self, ref_path: str, test_path: str, config) -> MetricResult:
            return MetricResult(value=0.24, meta={"metric": "dists", "device": "cpu"})

    def _get(name: str):
        if name == "lpips":
            return DummyLpips()
        if name == "dists":
            return DummyDists()
        raise KeyError(name)

    monkeypatch.setattr(compare_routes.registry, "get", _get)
    client = _client_with_debug(debug=True)

    r = client.post(
        "/compare",
        json={
            "ref_path": "tests/assets/ref_1.png",
            "test_path": "tests/assets/test_1.png",
            "config": {"lpips_net": "vgg", "force_device": "cpu"},
        },
    )

    assert r.status_code == 200
    assert r.headers["content-type"].startswith("application/json")
    body = r.json()
    assert set(body.keys()) == {"lpips", "dists", "lpips_heatmap_png_base64"}
    assert set(body["lpips"].keys()) == {"value", "meta"}
    assert set(body["dists"].keys()) == {"value", "meta"}
    assert isinstance(body["lpips_heatmap_png_base64"], str)


def test_contract_compare_lpips_success_shape(monkeypatch):
    import app.api.routes.compare as compare_routes
    from app.metrics.base import Metric, MetricResult

    class DummyLpips(Metric):
        name = "lpips"

        def distance(self, ref_path: str, test_path: str, config) -> MetricResult:
            return MetricResult(value=0.42, meta={"metric": "lpips", "device": "cpu"})

        def heatmap_png(self, ref_path: str, test_path: str, config) -> bytes:
            return b"\x89PNG\r\n\x1a\n"

    monkeypatch.setattr(compare_routes.registry, "get", lambda name: DummyLpips())
    client = _client_with_debug(debug=True)

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
    assert set(body.keys()) == {"lpips", "lpips_heatmap_png_base64"}
    assert set(body["lpips"].keys()) == {"value", "meta"}


def test_contract_compare_dists_success_shape(monkeypatch):
    import app.api.routes.compare as compare_routes
    from app.metrics.base import Metric, MetricResult

    class DummyDists(Metric):
        name = "dists"

        def distance(self, ref_path: str, test_path: str, config) -> MetricResult:
            return MetricResult(value=0.24, meta={"metric": "dists", "device": "cpu"})

    monkeypatch.setattr(compare_routes.registry, "get", lambda name: DummyDists())
    client = _client_with_debug(debug=True)

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
    assert set(body["dists"].keys()) == {"value", "meta"}


def test_contract_compare_validation_error_shape():
    client = _client_with_debug(debug=True)

    r = client.post(
        "/compare/lpips",
        json={
            "ref_path": "tests/assets/ref_1.png",
            "test_path": "tests/assets/test_1.png",
            "config": {"net": "invalid"},
        },
    )

    assert r.status_code == 422
    body = r.json()
    assert set(body.keys()) == {"detail"}
    assert isinstance(body["detail"], list)
    assert body["detail"]
    first = body["detail"][0]
    assert {"type", "loc", "msg"}.issubset(first.keys())


def test_contract_compare_404_error_shape(monkeypatch):
    import app.api.routes.compare as compare_routes
    from app.metrics.base import Metric

    class DummyMetric(Metric):
        name = "dists"

        def distance(self, ref_path: str, test_path: str, config):
            raise FileNotFoundError("missing.png")

    monkeypatch.setattr(compare_routes.registry, "get", lambda name: DummyMetric())
    client = _client_with_debug(debug=True)

    r = client.post(
        "/compare/dists",
        json={
            "ref_path": "tests/assets/ref_1.png",
            "test_path": "tests/assets/test_1.png",
            "config": {"force_device": "cpu"},
        },
    )

    assert r.status_code == 404
    assert set(r.json().keys()) == {"detail"}


def test_contract_compare_403_error_shape(monkeypatch):
    import app.api.routes.compare as compare_routes
    from app.metrics.base import Metric

    class DummyMetric(Metric):
        name = "lpips"

        def distance(self, ref_path: str, test_path: str, config):
            raise PermissionError("Path is outside IMAGE_BASE_DIR: /etc/passwd")

    monkeypatch.setattr(compare_routes.registry, "get", lambda name: DummyMetric())
    client = _client_with_debug(debug=True)

    r = client.post(
        "/compare/lpips",
        json={
            "ref_path": "tests/assets/ref_1.png",
            "test_path": "tests/assets/test_1.png",
            "config": {"net": "vgg", "force_device": "cpu"},
        },
    )

    assert r.status_code == 403
    assert set(r.json().keys()) == {"detail"}


def test_contract_compare_500_shape_api_debug_off(monkeypatch):
    import app.api.routes.compare as compare_routes
    from app.metrics.base import Metric

    class DummyMetric(Metric):
        name = "dists"

        def distance(self, ref_path: str, test_path: str, config):
            raise RuntimeError("sensitive details")

    monkeypatch.setattr(compare_routes.registry, "get", lambda name: DummyMetric())
    client = _client_with_debug(debug=False)

    r = client.post(
        "/compare/dists",
        json={
            "ref_path": "tests/assets/ref_1.png",
            "test_path": "tests/assets/test_1.png",
            "config": {"force_device": "cpu"},
        },
    )

    assert r.status_code == 500
    assert r.headers["content-type"].startswith("text/plain")
    assert r.text == "Internal Server Error"


def test_contract_compare_500_shape_api_debug_on(monkeypatch):
    import app.api.routes.compare as compare_routes
    from app.metrics.base import Metric

    class DummyMetric(Metric):
        name = "dists"

        def distance(self, ref_path: str, test_path: str, config):
            raise RuntimeError("boom")

    monkeypatch.setattr(compare_routes.registry, "get", lambda name: DummyMetric())
    client = _client_with_debug(debug=True)

    r = client.post(
        "/compare/dists",
        json={
            "ref_path": "tests/assets/ref_1.png",
            "test_path": "tests/assets/test_1.png",
            "config": {"force_device": "cpu"},
        },
    )

    assert r.status_code == 500
    body = r.json()
    assert set(body.keys()) == {"error", "detail", "path", "method"}
    assert body["error"] == "RuntimeError"
    assert body["path"] == "/compare/dists"
    assert body["method"] == "POST"
