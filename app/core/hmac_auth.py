from __future__ import annotations

import hashlib
import hmac
import threading
import time

from fastapi import HTTPException, Request

from app.core.config import get_bool, get_int, get_str

_TIMESTAMP_HEADER = "X-HMAC-Timestamp"
_NONCE_HEADER = "X-HMAC-Nonce"
_SIGNATURE_HEADER = "X-HMAC-Signature"

_nonce_lock = threading.Lock()
_nonce_expiry_ms: dict[str, int] = {}


def hmac_enabled() -> bool:
    return get_bool("HMAC_ENABLED", default=False)


def validate_hmac_settings() -> None:
    if not hmac_enabled():
        return

    secret = get_str("HMAC_SECRET", "").strip()
    if not secret:
        raise RuntimeError("HMAC is enabled but HMAC_SECRET is empty")

    allowed_skew_sec = get_int("HMAC_ALLOWED_SKEW_SEC", 300)
    if allowed_skew_sec <= 0:
        raise RuntimeError("HMAC_ALLOWED_SKEW_SEC must be > 0")

    nonce_ttl_sec = get_int("HMAC_NONCE_TTL_SEC", allowed_skew_sec)
    if nonce_ttl_sec <= 0:
        raise RuntimeError("HMAC_NONCE_TTL_SEC must be > 0")


def _reject(detail: str) -> None:
    raise HTTPException(status_code=401, detail=detail)


def _build_canonical_message(
    request: Request,
    *,
    fields: dict[str, str],
    timestamp: str,
    nonce: str,
) -> str:
    lines: list[str] = [
        request.method.upper(),
        request.url.path,
        f"query={request.url.query}",
    ]
    for key in sorted(fields):
        lines.append(f"{key}={fields[key]}")
    lines.append(f"timestamp={timestamp}")
    lines.append(f"nonce={nonce}")
    return "\n".join(lines)


def _validate_timestamp(timestamp_value: str, allowed_skew_sec: int) -> None:
    try:
        timestamp = int(timestamp_value)
    except ValueError:
        _reject("Invalid HMAC timestamp")

    now = int(time.time())
    if abs(now - timestamp) > allowed_skew_sec:
        _reject("HMAC timestamp is outside allowed skew")


def _remember_nonce(nonce: str, ttl_sec: int) -> None:
    now_ms = int(time.time() * 1000)
    expires_at_ms = now_ms + ttl_sec * 1000

    with _nonce_lock:
        stale = [k for k, expiry in _nonce_expiry_ms.items() if expiry <= now_ms]
        for key in stale:
            _nonce_expiry_ms.pop(key, None)

        if nonce in _nonce_expiry_ms:
            _reject("HMAC nonce replay detected")

        _nonce_expiry_ms[nonce] = expires_at_ms


def verify_hmac_request(request: Request, *, fields: dict[str, str] | None = None) -> None:
    if not hmac_enabled():
        return

    secret = get_str("HMAC_SECRET", "").strip()
    if not secret:
        raise HTTPException(status_code=503, detail="HMAC is enabled but not configured")

    timestamp = request.headers.get(_TIMESTAMP_HEADER, "").strip()
    nonce = request.headers.get(_NONCE_HEADER, "").strip()
    signature = request.headers.get(_SIGNATURE_HEADER, "").strip().lower()

    if not timestamp:
        _reject(f"Missing header: {_TIMESTAMP_HEADER}")
    if not signature:
        _reject(f"Missing header: {_SIGNATURE_HEADER}")

    allowed_skew_sec = get_int("HMAC_ALLOWED_SKEW_SEC", 300)
    _validate_timestamp(timestamp, allowed_skew_sec)

    require_nonce = get_bool("HMAC_REQUIRE_NONCE", default=True)
    nonce_ttl_sec = get_int("HMAC_NONCE_TTL_SEC", allowed_skew_sec)

    if require_nonce and not nonce:
        _reject(f"Missing header: {_NONCE_HEADER}")
    if not nonce:
        nonce = "-"

    canonical = _build_canonical_message(
        request,
        fields=fields or {},
        timestamp=timestamp,
        nonce=nonce,
    )
    expected = hmac.new(secret.encode("utf-8"), canonical.encode("utf-8"), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, signature):
        _reject("Invalid HMAC signature")

    if require_nonce:
        _remember_nonce(nonce, nonce_ttl_sec)


def _clear_nonce_cache() -> None:
    with _nonce_lock:
        _nonce_expiry_ms.clear()
