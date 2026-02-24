from __future__ import annotations

from collections.abc import Iterator

import pytest

from app.core import build_info
from app.core import config as app_config
from app.main import create_app


@pytest.fixture(autouse=True)
def _clear_cached_config() -> Iterator[None]:
    app_config._clear_config_cache()
    build_info._clear_git_metadata_cache()
    yield
    app_config._clear_config_cache()
    build_info._clear_git_metadata_cache()


def test_config_toml_values_are_used_when_env_is_missing(monkeypatch: pytest.MonkeyPatch, tmp_path):
    cfg = tmp_path / "config.toml"
    cfg.write_text(
        """
[env]
API_DEBUG = "0"
LOG_API_ENABLED = true
LOG_API_TIMEOUT_MS = 3500
COMPARE_JOB_WORKERS = 3
QUEUE_MAXSIZE = 25
""".strip(),
        encoding="utf-8",
    )
    monkeypatch.setenv("APP_CONFIG_FILE", str(cfg))

    assert app_config.get_bool("API_DEBUG", default=True) is False
    assert app_config.get_bool("LOG_API_ENABLED", default=False) is True
    assert app_config.get_int("LOG_API_TIMEOUT_MS", 2000) == 3500
    assert app_config.get_int("COMPARE_JOB_WORKERS", 2) == 3
    assert app_config.get_int("QUEUE_MAXSIZE", 0) == 25


def test_system_env_has_priority_over_config_file(monkeypatch: pytest.MonkeyPatch, tmp_path):
    cfg = tmp_path / "config.toml"
    cfg.write_text(
        """
[env]
COMPARE_JOB_WORKERS = 2
QUEUE_MAXSIZE = 10
""".strip(),
        encoding="utf-8",
    )
    monkeypatch.setenv("APP_CONFIG_FILE", str(cfg))
    monkeypatch.setenv("COMPARE_JOB_WORKERS", "6")

    assert app_config.get_int("COMPARE_JOB_WORKERS", 2) == 6
    assert app_config.get_int("QUEUE_MAXSIZE", 0) == 10


def test_create_app_reads_job_settings_from_config_file(monkeypatch: pytest.MonkeyPatch, tmp_path):
    cfg = tmp_path / "config.toml"
    cfg.write_text(
        """
[env]
COMPARE_JOB_WORKERS = 4
QUEUE_MAXSIZE = 7
""".strip(),
        encoding="utf-8",
    )
    monkeypatch.setenv("APP_CONFIG_FILE", str(cfg))

    app = create_app()
    jobs_manager = app.state.compare_jobs

    assert jobs_manager._workers_count == 4
    assert jobs_manager._queue.maxsize == 7


def test_create_app_clamps_invalid_job_settings(monkeypatch: pytest.MonkeyPatch, tmp_path):
    cfg = tmp_path / "config.toml"
    cfg.write_text(
        """
[env]
COMPARE_JOB_WORKERS = -3
QUEUE_MAXSIZE = -1
""".strip(),
        encoding="utf-8",
    )
    monkeypatch.setenv("APP_CONFIG_FILE", str(cfg))

    app = create_app()
    jobs_manager = app.state.compare_jobs

    assert jobs_manager._workers_count == 1
    assert jobs_manager._queue.maxsize == 0


def test_create_app_caps_too_high_worker_count(monkeypatch: pytest.MonkeyPatch, tmp_path):
    cfg = tmp_path / "config.toml"
    cfg.write_text(
        """
[env]
COMPARE_JOB_WORKERS = 100
QUEUE_MAXSIZE = 5
""".strip(),
        encoding="utf-8",
    )
    monkeypatch.setenv("APP_CONFIG_FILE", str(cfg))
    monkeypatch.setattr("app.main.os.cpu_count", lambda: 2)

    app = create_app()
    jobs_manager = app.state.compare_jobs

    assert jobs_manager._workers_count == 8
    assert jobs_manager._queue.maxsize == 5


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
