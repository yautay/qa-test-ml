from __future__ import annotations

import json
from contextlib import contextmanager
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
    captured: dict[str, object] = {}

    class _FakeResponse:
        status = 200
        reason = "OK"

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

    def _fake_urlopen(request, timeout=None):
        captured["url"] = request.full_url
        captured["body"] = json.loads(request.data)
        captured["headers"] = dict(request.headers)
        captured["timeout"] = timeout
        return _FakeResponse()

    monkeypatch.setattr("app.core.logging.urllib.request.urlopen", _fake_urlopen)

    sink = ApiLogSink(
        "http://logs.local/ingest",
        service_name="svc",
        timeout_ms=1500,
        token="topsecret",
    )
    sink.write(_DummyMessage())

    assert captured["url"] == "http://logs.local/ingest"
    payload = captured["body"]
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
    # urllib capitalises header names (e.g. Content-type); compare case-insensitively
    headers_lower = {k.lower(): v for k, v in captured["headers"].items()}
    assert headers_lower["content-type"] == "application/json"
    assert headers_lower["authorization"] == "Bearer topsecret"


def test_api_log_sink_swallows_post_errors(monkeypatch):
    def _raising_urlopen(request, timeout=None):
        raise TimeoutError("network timeout")

    monkeypatch.setattr("app.core.logging.urllib.request.urlopen", _raising_urlopen)

    sink = ApiLogSink("http://logs.local/ingest", service_name="svc", timeout_ms=1500)
    sink.write(_DummyMessage())
