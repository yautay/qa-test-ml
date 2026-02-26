from __future__ import annotations

import sys
import threading
from typing import Any

import httpx
from loguru import logger

from app.core.build_info import get_git_metadata
from app.core.config import get_bool, get_int, get_str


class ApiLogSink:
    def __init__(
        self,
        url: str,
        *,
        service_name: str,
        timeout_ms: int,
        token: str | None = None,
    ):
        self.url = url
        self.service_name = service_name
        self.timeout = max(100, timeout_ms) / 1000.0
        self.token = token
        self._lock = threading.Lock()
        self._error_count = 0

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    def _payload(self, message: Any) -> dict[str, Any]:
        record = message.record
        exception = None
        if record["exception"] is not None:
            exception = str(record["exception"])

        extra = record["extra"]
        class_name = extra.get("class_name")
        method_name = extra.get("method_name") or record["function"]

        return {
            "timestamp": record["time"].isoformat(),
            "level": record["level"].name,
            "message": record["message"],
            "service": self.service_name,
            "branch": extra.get("branch"),
            "file": record["file"].name,
            "class": class_name,
            "method": method_name,
            "module": record["module"],
            "function": record["function"],
            "line": record["line"],
            "exception": exception,
            "extra": extra,
        }

    def write(self, message: Any) -> None:
        payload = self._payload(message)
        headers = self._headers()

        try:
            with httpx.Client(timeout=self.timeout) as client:
                client.post(self.url, json=payload, headers=headers)
            with self._lock:
                self._error_count = 0
        except Exception:
            with self._lock:
                self._error_count += 1
                should_report = self._error_count in {1, 5, 10} or self._error_count % 50 == 0
            if should_report:
                sys.stderr.write(f"[loguru] API sink post failed ({self._error_count}) url={self.url}\n")


def configure_logging() -> None:
    logger.remove()
    git_branch = get_git_metadata().branch

    def _patch_record(record: dict[str, Any]) -> None:
        extra = record["extra"]
        extra.setdefault("branch", git_branch)
        extra.setdefault("class_name", None)
        extra.setdefault("method_name", record["function"])

    logger.configure(patcher=_patch_record)  # type: ignore[arg-type]

    log_level = get_str("LOG_LEVEL", "INFO")
    logger.add(
        sys.stderr,
        level=log_level,
        enqueue=True,
        backtrace=False,
        diagnose=False,
        format="<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
        "<magenta>{extra[branch]}</magenta> | "
        "<level>{level: <8}</level> | "
        "<cyan>{file.name}</cyan>:<cyan>{extra[class_name]}</cyan>:<cyan>{extra[method_name]}</cyan>:"
        "<cyan>{line}</cyan> - "
        "<level>{message}</level>",
    )

    api_enabled = get_bool("LOG_API_ENABLED", default=False)
    api_url = get_str("LOG_API_URL", "").strip()
    if api_enabled and api_url:
        api_level = get_str("LOG_API_LEVEL", "ERROR")
        timeout_ms = get_int("LOG_API_TIMEOUT_MS", 2000)
        token = get_str("LOG_API_TOKEN", "").strip() or None
        service_name = get_str("LOG_SERVICE_NAME", "perceptual-metrics-service")

        sink = ApiLogSink(
            api_url,
            service_name=service_name,
            timeout_ms=timeout_ms,
            token=token,
        )
        logger.add(
            sink.write,
            level=api_level,
            enqueue=True,
            backtrace=False,
            diagnose=False,
        )
