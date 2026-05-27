"""
Unit tests for app.core.metric_names and the health endpoint's
torch-free import path.

Goals:
- KNOWN_METRIC_NAMES contains the expected metric identifiers.
- Importing app.core.metric_names does NOT trigger a torch import.
- health.py no longer imports app.core.registry (which carries torch).
- /health returns the correct metric list sourced from KNOWN_METRIC_NAMES.
"""
from __future__ import annotations

import sys
import types

import pytest
from fastapi.testclient import TestClient

from app.core import config as app_config
from app.core import job_store as job_store_module
from app.core.metric_names import KNOWN_METRIC_NAMES


# ---------------------------------------------------------------------------
# Isolation fixture (mirrors the pattern used across the test suite)
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _runtime(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("JOB_STORE_BACKEND", "memory")
    app_config._clear_config_cache()
    job_store_module._clear_job_store_cache()
    yield
    app_config._clear_config_cache()
    job_store_module._clear_job_store_cache()


# ---------------------------------------------------------------------------
# 1. Static content of KNOWN_METRIC_NAMES
# ---------------------------------------------------------------------------


def test_known_metric_names_contains_lpips():
    assert "lpips" in KNOWN_METRIC_NAMES


def test_known_metric_names_contains_dists():
    assert "dists" in KNOWN_METRIC_NAMES


def test_known_metric_names_is_list_of_strings():
    assert isinstance(KNOWN_METRIC_NAMES, list)
    assert all(isinstance(name, str) for name in KNOWN_METRIC_NAMES)


def test_known_metric_names_has_no_duplicates():
    assert len(KNOWN_METRIC_NAMES) == len(set(KNOWN_METRIC_NAMES))


# ---------------------------------------------------------------------------
# 2. Import isolation — torch must NOT be loaded by metric_names or health
# ---------------------------------------------------------------------------


def test_metric_names_module_does_not_import_torch():
    """Importing metric_names must not pull torch into sys.modules."""
    # Remove torch from sys.modules if somehow already present in this
    # lightweight test process so the assertion is meaningful.
    torch_keys = [k for k in sys.modules if k == "torch" or k.startswith("torch.")]
    for k in torch_keys:
        sys.modules.pop(k, None)

    # Re-import the module under test (force reload to re-run module body)
    import importlib

    import app.core.metric_names as mn

    importlib.reload(mn)

    assert "torch" not in sys.modules, (
        "torch was imported as a side-effect of loading app.core.metric_names"
    )


def test_health_route_module_does_not_import_registry(monkeypatch: pytest.MonkeyPatch):
    """
    app.api.routes.health must not import app.core.registry.
    Registry carries eager torch imports and must stay worker-only.
    """
    import importlib

    # Stub out registry so that IF it were imported it would be detectable
    # but would not crash (torch is absent in the unit-test environment).
    fake_registry_module = types.ModuleType("app.core.registry")
    fake_registry_module.registry = object()  # type: ignore[attr-defined]

    registry_imported = []

    original_import = __builtins__.__import__ if hasattr(__builtins__, "__import__") else __import__  # type: ignore[union-attr]

    def _tracking_import(name, *args, **kwargs):
        if name == "app.core.registry":
            registry_imported.append(name)
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr("builtins.__import__", _tracking_import)

    # Force reload of the health route module to re-execute its imports
    import app.api.routes.health as health_mod

    importlib.reload(health_mod)

    assert registry_imported == [], (
        "app.api.routes.health imported app.core.registry — "
        "this would load torch into the API process"
    )


# ---------------------------------------------------------------------------
# 3. /health endpoint returns metrics sourced from KNOWN_METRIC_NAMES
# ---------------------------------------------------------------------------


def test_health_metrics_match_known_metric_names():
    """The /health response's metrics list must equal sorted(KNOWN_METRIC_NAMES)."""
    from app.main import create_app

    client = TestClient(create_app())
    r = client.get("/health")

    assert r.status_code == 200
    assert r.json()["metrics"] == sorted(KNOWN_METRIC_NAMES)


def test_health_metrics_list_is_sorted():
    """/health metrics must be returned in alphabetical order."""
    from app.main import create_app

    client = TestClient(create_app())
    r = client.get("/health")

    metrics = r.json()["metrics"]
    assert metrics == sorted(metrics)


def test_health_metrics_list_is_not_empty():
    from app.main import create_app

    client = TestClient(create_app())
    r = client.get("/health")

    assert len(r.json()["metrics"]) > 0
