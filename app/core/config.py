from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover
    import tomli as tomllib


_TRUE_VALUES = {"1", "true", "yes", "on"}
_FALSE_VALUES = {"0", "false", "no", "off"}


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _config_file_path() -> Path:
    custom_path = os.getenv("APP_CONFIG_FILE")
    if custom_path:
        return Path(custom_path).expanduser().resolve()
    return _project_root() / "config.toml"


@lru_cache(maxsize=1)
def _file_env_values() -> dict[str, str]:
    if tomllib is None:
        return {}

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


def _clear_config_cache() -> None:
    _file_env_values.cache_clear()
