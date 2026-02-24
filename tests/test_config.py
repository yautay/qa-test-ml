from __future__ import annotations

from collections.abc import Iterator

import pytest

from app.core import build_info
from app.core import config as app_config
from app.core import job_store as app_job_store
from app.main import create_app


@pytest.fixture(autouse=True)
def _clear_cached_config() -> Iterator[None]:
    app_config._clear_config_cache()
    app_job_store._clear_job_store_cache()
    build_info._clear_git_metadata_cache()
    yield
    app_config._clear_config_cache()
    app_job_store._clear_job_store_cache()
    build_info._clear_git_metadata_cache()


def test_config_toml_values_are_used_when_env_is_missing(monkeypatch: pytest.MonkeyPatch, tmp_path):
    cfg = tmp_path / "config.toml"
    cfg.write_text(
        """
[env]
API_DEBUG = "0"
LOG_API_ENABLED = true
LOG_API_TIMEOUT_MS = 3500
JOB_STORE_BACKEND = "memory"
JOB_TTL_SEC = 120
""".strip(),
        encoding="utf-8",
    )
    monkeypatch.setenv("APP_CONFIG_FILE", str(cfg))

    assert app_config.get_bool("API_DEBUG", default=True) is False
    assert app_config.get_bool("LOG_API_ENABLED", default=False) is True
    assert app_config.get_int("LOG_API_TIMEOUT_MS", 2000) == 3500
    assert app_config.get_str("JOB_STORE_BACKEND", "redis") == "memory"
    assert app_config.get_int("JOB_TTL_SEC", 86400) == 120


def test_system_env_has_priority_over_config_file(monkeypatch: pytest.MonkeyPatch, tmp_path):
    cfg = tmp_path / "config.toml"
    cfg.write_text(
        """
[env]
REDIS_PREFIX = "cfg-prefix"
""".strip(),
        encoding="utf-8",
    )
    monkeypatch.setenv("APP_CONFIG_FILE", str(cfg))
    monkeypatch.setenv("REDIS_PREFIX", "env-prefix")

    assert app_config.get_str("REDIS_PREFIX", "pms") == "env-prefix"


def test_create_app_reads_job_settings_from_config_file(monkeypatch: pytest.MonkeyPatch, tmp_path):
    cfg = tmp_path / "config.toml"
    cfg.write_text(
        """
[env]
JOB_STORE_BACKEND = "memory"
""".strip(),
        encoding="utf-8",
    )
    monkeypatch.setenv("APP_CONFIG_FILE", str(cfg))

    app = create_app()
    job_store = app.state.job_store

    assert job_store is not None


def test_create_app_with_memory_job_store_backend(monkeypatch: pytest.MonkeyPatch, tmp_path):
    cfg = tmp_path / "config.toml"
    cfg.write_text(
        """
[env]
JOB_STORE_BACKEND = "memory"
""".strip(),
        encoding="utf-8",
    )
    monkeypatch.setenv("APP_CONFIG_FILE", str(cfg))

    app = create_app()
    job_store = app.state.job_store

    assert job_store is not None


def test_create_app_with_redis_job_store_backend(monkeypatch: pytest.MonkeyPatch, tmp_path):
    cfg = tmp_path / "config.toml"
    cfg.write_text(
        """
[env]
JOB_STORE_BACKEND = "redis"
REDIS_URL = "redis://127.0.0.1:6379/0"
""".strip(),
        encoding="utf-8",
    )
    monkeypatch.setenv("APP_CONFIG_FILE", str(cfg))

    app = create_app()
    job_store = app.state.job_store

    assert job_store is not None


def test_git_metadata_uses_env_overrides(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("APP_GIT_BRANCH", "release/1.2")
    monkeypatch.setenv("APP_GIT_TAG", "v1.2.3")
    monkeypatch.setenv("APP_GIT_LAST_COMMIT", "abc123")
    monkeypatch.setenv("APP_GIT_COMMITTER", "Jane Doe")
    monkeypatch.setenv("APP_GIT_COMMIT_DATE", "2026-02-24T10:00:00+00:00")

    metadata = build_info.get_git_metadata()

    assert metadata.branch == "release/1.2"
    assert metadata.tag == "v1.2.3"
    assert metadata.last_commit == "abc123"
    assert metadata.committer == "Jane Doe"
    assert metadata.date == "2026-02-24T10:00:00+00:00"
