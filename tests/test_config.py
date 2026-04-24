from __future__ import annotations

from collections.abc import Iterator

import pytest

from app.core import build_info
from app.core import config as app_config
from app.core import job_store as app_job_store
from app.core.celery_app import create_celery_app
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


def test_redis_connection_settings_prefer_redis_url(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("REDIS_URL", "redis://url-user:url-pass@redis-url:6380/5")
    monkeypatch.setenv("REDIS_HOST", "split-host")
    monkeypatch.setenv("REDIS_PORT", "6390")
    monkeypatch.setenv("REDIS_DB", "6")
    monkeypatch.setenv("REDIS_USERNAME", "split-user")
    monkeypatch.setenv("REDIS_PASSWORD", "split-pass")
    monkeypatch.setenv("REDIS_TLS", "true")

    settings = app_config.get_redis_connection_settings()

    assert settings.url == "redis://url-user:url-pass@redis-url:6380/5"
    assert settings.source == "redis_url"
    assert settings.tls_enabled is False
    assert settings.username_configured is True
    assert settings.password_configured is True


def test_redis_connection_settings_fall_back_to_split_vars(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("REDIS_URL", raising=False)
    monkeypatch.setenv("REDIS_HOST", "redis.internal")
    monkeypatch.setenv("REDIS_PORT", "6380")
    monkeypatch.setenv("REDIS_DB", "2")
    monkeypatch.setenv("REDIS_USERNAME", "svc-user")
    monkeypatch.setenv("REDIS_PASSWORD", "super-secret")
    monkeypatch.setenv("REDIS_TLS", "true")

    settings = app_config.get_redis_connection_settings()

    assert settings.url == "rediss://svc-user:super-secret@redis.internal:6380/2"
    assert settings.source == "split_vars"
    assert settings.tls_enabled is True
    assert settings.username_configured is True
    assert settings.password_configured is True


def test_redis_connection_settings_accept_rediss_url(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("REDIS_URL", "rediss://redis-user:redis-pass@secure-redis:6379/0")

    settings = app_config.get_redis_connection_settings()

    assert settings.url == "rediss://redis-user:redis-pass@secure-redis:6379/0"
    assert settings.tls_enabled is True


@pytest.mark.parametrize(
    ("env_name", "env_value", "error_message"),
    [
        ("REDIS_PORT", "abc", "REDIS_PORT must be an integer"),
        ("REDIS_PORT", "", "REDIS_PORT must not be empty"),
        ("REDIS_DB", "abc", "REDIS_DB must be an integer"),
        ("REDIS_DB", "", "REDIS_DB must not be empty"),
    ],
)
def test_redis_connection_settings_reject_invalid_split_ints(
    monkeypatch: pytest.MonkeyPatch,
    env_name: str,
    env_value: str,
    error_message: str,
):
    monkeypatch.delenv("REDIS_URL", raising=False)
    monkeypatch.setenv(env_name, env_value)

    with pytest.raises(RuntimeError, match=error_message):
        app_config.get_redis_connection_settings()


def test_redis_connection_settings_reject_invalid_redis_url_scheme(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("REDIS_URL", "http://user:topsecret@redis.example:6379/0")

    with pytest.raises(RuntimeError, match="REDIS_URL"):
        app_config.get_redis_connection_settings()


def test_redis_connection_settings_reject_username_without_password(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("REDIS_URL", raising=False)
    monkeypatch.setenv("REDIS_USERNAME", "svc-user")
    monkeypatch.delenv("REDIS_PASSWORD", raising=False)

    with pytest.raises(RuntimeError, match="REDIS_PASSWORD") as exc_info:
        app_config.get_redis_connection_settings()

    assert "svc-user" not in str(exc_info.value)


def test_mask_redis_url_hides_password(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("REDIS_URL", "rediss://svc-user:super-secret@redis.example:6379/0")

    settings = app_config.get_redis_connection_settings()
    masked = app_config.mask_redis_url(settings.url)

    assert masked == "rediss://svc-user:***@redis.example:6379/0"
    assert "super-secret" not in masked


def test_create_celery_app_uses_shared_redis_settings_when_explicit_urls_are_absent(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("CELERY_BROKER_URL", raising=False)
    monkeypatch.delenv("CELERY_RESULT_BACKEND", raising=False)
    monkeypatch.delenv("REDIS_URL", raising=False)
    monkeypatch.setenv("REDIS_HOST", "redis.internal")
    monkeypatch.setenv("REDIS_PORT", "6380")
    monkeypatch.setenv("REDIS_DB", "3")
    monkeypatch.setenv("REDIS_PASSWORD", "shared-secret")
    monkeypatch.setenv("REDIS_TLS", "true")

    celery_app = create_celery_app()

    assert celery_app.conf.broker_url == "rediss://:shared-secret@redis.internal:6380/3"
    assert celery_app.conf.result_backend == "rediss://:shared-secret@redis.internal:6380/3"


def test_create_celery_app_prefers_explicit_celery_urls(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("CELERY_BROKER_URL", "redis://broker.example:6379/7")
    monkeypatch.setenv("CELERY_RESULT_BACKEND", "redis://backend.example:6379/8")
    monkeypatch.setenv("REDIS_URL", "redis://shared.example:6379/0")

    celery_app = create_celery_app()

    assert celery_app.conf.broker_url == "redis://broker.example:6379/7"
    assert celery_app.conf.result_backend == "redis://backend.example:6379/8"


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


def test_create_app_fails_when_hmac_enabled_without_secret(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("HMAC_ENABLED", "true")
    monkeypatch.delenv("HMAC_SECRET", raising=False)

    with pytest.raises(RuntimeError, match="HMAC_SECRET"):
        create_app()
