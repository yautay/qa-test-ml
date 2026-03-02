from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace

from app.core.logging import ApiLogSink


class _DummyMessage:
    def __init__(self):
        self.record = {
            "time": datetime.now(),
            "level": SimpleNamespace(name="ERROR"),
            "message": "boom",
            "file": SimpleNamespace(name="main.py"),
            "module": "main",
            "function": "handler",
            "line": 42,
            "exception": RuntimeError("failure"),
            "extra": {
                "job_id": "123",
                "branch": "feature/test",
                "class_name": "CompareService",
                "method_name": "handle_request",
            },
        }


def test_api_log_sink_posts_expected_payload(monkeypatch):
    posted: dict[str, object] = {}

    class DummyResponse:
        def raise_for_status(self):
            return None

    class DummyClient:
        def __init__(self, timeout: float):
            self.timeout = timeout

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def post(self, url: str, json: dict[str, object], headers: dict[str, str]):
            posted["url"] = url
            posted["json"] = json
            posted["headers"] = headers
            return DummyResponse()

    monkeypatch.setattr("app.core.logging.httpx.Client", DummyClient)

    sink = ApiLogSink(
        "http://logs.local/ingest",
        service_name="svc",
        timeout_ms=1500,
        token="topsecret",
    )
    sink.write(_DummyMessage())

    assert posted["url"] == "http://logs.local/ingest"
    payload = posted["json"]
    assert isinstance(payload, dict)
    assert payload["service"] == "svc"
    assert payload["level"] == "ERROR"
    assert payload["message"] == "boom"
    assert payload["branch"] == "feature/test"
    assert payload["file"] == "main.py"
    assert payload["class"] == "CompareService"
    assert payload["method"] == "handle_request"
    assert payload["exception"] == "failure"
    assert payload["extra"] == {
        "job_id": "123",
        "branch": "feature/test",
        "class_name": "CompareService",
        "method_name": "handle_request",
    }
    assert posted["headers"] == {
        "Content-Type": "application/json",
        "Authorization": "Bearer topsecret",
    }


def test_api_log_sink_swallows_post_errors(monkeypatch):
    class DummyResponse:
        def raise_for_status(self):
            raise TimeoutError("network timeout")

    class DummyClient:
        def __init__(self, timeout: float):
            self.timeout = timeout

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def post(self, url: str, json: dict[str, object], headers: dict[str, str]):
            return DummyResponse()

    monkeypatch.setattr("app.core.logging.httpx.Client", DummyClient)

    sink = ApiLogSink("http://logs.local/ingest", service_name="svc", timeout_ms=1500)
    sink.write(_DummyMessage())
