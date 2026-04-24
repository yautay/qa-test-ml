from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal
from urllib.parse import quote, urlsplit, urlunsplit

try:
    import tomllib
except ModuleNotFoundError:  # Python < 3.11
    import tomli as tomllib  # type: ignore[no-redef]

_TRUE_VALUES = {"1", "true", "yes", "on"}
_FALSE_VALUES = {"0", "false", "no", "off"}
_REDIS_DEFAULT_HOST = "127.0.0.1"
_REDIS_DEFAULT_PORT = 6379
_REDIS_DEFAULT_DB = 0
_REDIS_ALLOWED_SCHEMES = {"redis", "rediss"}


@dataclass(frozen=True)
class RedisConnectionSettings:
    url: str
    source: Literal["redis_url", "split_vars"]
    tls_enabled: bool
    username_configured: bool
    password_configured: bool


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _config_file_path() -> Path:
    custom_path = os.getenv("APP_CONFIG_FILE")
    if custom_path:
        return Path(custom_path).expanduser().resolve()
    return _project_root() / "config.toml"


@lru_cache(maxsize=1)
def _file_env_values() -> dict[str, str]:
    config_path = _config_file_path()
    if not config_path.exists() or not config_path.is_file():
        return {}

    try:
        raw = config_path.read_text(encoding="utf-8")
        parsed = tomllib.loads(raw)
    except (OSError, tomllib.TOMLDecodeError):
        return {}

    env_section: Any = parsed.get("env", {})
    if not isinstance(env_section, dict):
        return {}

    values: dict[str, str] = {}
    for key, value in env_section.items():
        if not isinstance(key, str):
            continue
        if isinstance(value, bool):
            values[key] = "true" if value else "false"
            continue
        values[key] = str(value)

    return values


def _resolve_raw(name: str) -> str | None:
    env_value = os.getenv(name)
    if env_value is not None:
        return env_value
    return _file_env_values().get(name)


def get_str(name: str, default: str = "") -> str:
    value = _resolve_raw(name)
    if value is None:
        return default
    return value


def get_bool(name: str, default: bool = False) -> bool:
    value = _resolve_raw(name)
    if value is None:
        return default

    normalized = value.strip().lower()
    if normalized in _TRUE_VALUES:
        return True
    if normalized in _FALSE_VALUES:
        return False
    return default


def get_int(name: str, default: int) -> int:
    value = _resolve_raw(name)
    if value is None:
        return default

    try:
        return int(value)
    except ValueError:
        return default


def _require_non_blank(name: str, default: str) -> str:
    value = _resolve_raw(name)
    if value is None:
        return default

    normalized = value.strip()
    if not normalized:
        raise RuntimeError(f"{name} must not be empty")
    return normalized


def _parse_required_int(name: str, default: int) -> int:
    raw_value = _resolve_raw(name)
    if raw_value is None:
        return default

    value = raw_value.strip()
    if not value:
        raise RuntimeError(f"{name} must not be empty")

    try:
        return int(value)
    except ValueError as exc:
        raise RuntimeError(f"{name} must be an integer") from exc


def _validate_redis_url(url: str) -> RedisConnectionSettings:
    parsed = urlsplit(url)
    scheme = parsed.scheme.strip().lower()
    if scheme not in _REDIS_ALLOWED_SCHEMES:
        raise RuntimeError("REDIS_URL must use redis:// or rediss://")
    if not parsed.hostname:
        raise RuntimeError("REDIS_URL must include a Redis host")
    if parsed.path and parsed.path != "/":
        db_part = parsed.path.removeprefix("/")
        if not db_part.isdigit():
            raise RuntimeError("REDIS_URL database must be an integer")

    username_configured = parsed.username is not None and parsed.username != ""
    password_configured = parsed.password is not None and parsed.password != ""
    if username_configured and not password_configured:
        raise RuntimeError("REDIS_URL username requires a password")

    return RedisConnectionSettings(
        url=url,
        source="redis_url",
        tls_enabled=scheme == "rediss",
        username_configured=username_configured,
        password_configured=password_configured,
    )


def build_redis_url_from_split_vars() -> str:
    host = _require_non_blank("REDIS_HOST", _REDIS_DEFAULT_HOST)
    port = _parse_required_int("REDIS_PORT", _REDIS_DEFAULT_PORT)
    db = _parse_required_int("REDIS_DB", _REDIS_DEFAULT_DB)
    username = get_str("REDIS_USERNAME", "").strip()
    password = get_str("REDIS_PASSWORD", "").strip()
    tls_enabled = get_bool("REDIS_TLS", default=False)

    if port < 0:
        raise RuntimeError("REDIS_PORT must be >= 0")
    if db < 0:
        raise RuntimeError("REDIS_DB must be >= 0")
    if username and not password:
        raise RuntimeError("REDIS_PASSWORD must be set when REDIS_USERNAME is provided")

    auth = ""
    if username:
        auth = f"{quote(username, safe='')}:{quote(password, safe='')}@"
    elif password:
        auth = f":{quote(password, safe='')}@"

    scheme = "rediss" if tls_enabled else "redis"
    return f"{scheme}://{auth}{host}:{port}/{db}"


@lru_cache(maxsize=1)
def get_redis_connection_settings() -> RedisConnectionSettings:
    redis_url = get_str("REDIS_URL", "").strip()
    if redis_url:
        return _validate_redis_url(redis_url)

    url = build_redis_url_from_split_vars()
    parsed = urlsplit(url)
    return RedisConnectionSettings(
        url=url,
        source="split_vars",
        tls_enabled=parsed.scheme == "rediss",
        username_configured=bool(get_str("REDIS_USERNAME", "").strip()),
        password_configured=bool(get_str("REDIS_PASSWORD", "").strip()),
    )


def mask_redis_url(url: str) -> str:
    parsed = urlsplit(url)
    username = parsed.username or ""
    password_configured = parsed.password is not None and parsed.password != ""
    host = parsed.hostname or ""

    netloc = host
    if parsed.port is not None:
        netloc = f"{netloc}:{parsed.port}"

    if username:
        masked_auth = username
        if password_configured:
            masked_auth = f"{masked_auth}:***"
        netloc = f"{masked_auth}@{netloc}"
    elif password_configured:
        netloc = f":***@{netloc}"

    return urlunsplit((parsed.scheme, netloc, parsed.path, parsed.query, parsed.fragment))


def _clear_config_cache() -> None:
    _file_env_values.cache_clear()
    get_redis_connection_settings.cache_clear()
