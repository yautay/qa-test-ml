from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from loguru import logger
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from starlette.responses import Response

from app.api.routes.compare import router as compare_router
from app.api.routes.health import router as health_router
from app.core.build_info import get_git_metadata
from app.core.config import get_bool, get_int, get_redis_connection_settings, get_str, mask_redis_url
from app.core.hmac_auth import validate_hmac_settings
from app.core.job_store import get_job_store, get_redis_startup_check_mode, validate_redis_job_store_startup
from app.core.logging import configure_logging


def _read_runtime_settings() -> str:
    backend = get_str("JOB_STORE_BACKEND", "redis").strip().lower() or "redis"
    return backend


def _redis_startup_settings(backend: str) -> dict[str, object]:
    if backend != "redis":
        return {
            "redis_source": None,
            "redis_tls_enabled": False,
            "redis_username_configured": False,
            "redis_password_configured": False,
            "redis_url_masked": None,
            "redis_startup_check_mode": None,
        }

    redis_settings = get_redis_connection_settings()
    return {
        "redis_source": redis_settings.source,
        "redis_tls_enabled": redis_settings.tls_enabled,
        "redis_username_configured": redis_settings.username_configured,
        "redis_password_configured": redis_settings.password_configured,
        "redis_url_masked": mask_redis_url(redis_settings.url),
        "redis_startup_check_mode": get_redis_startup_check_mode(),
    }


def create_app() -> FastAPI:
    configure_logging()
    validate_hmac_settings()
    debug = get_bool("API_DEBUG", default=True)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        job_store_backend = _read_runtime_settings()
        store = get_job_store()
        app.state.job_store = store

        settings = {
            "api_debug": debug,
            "job_store_backend": job_store_backend,
            "image_base_dir": get_str("IMAGE_BASE_DIR", "."),
            **_redis_startup_settings(job_store_backend),
            "log_level": get_str("LOG_LEVEL", "INFO"),
            "log_api_enabled": get_bool("LOG_API_ENABLED", default=False),
            "log_api_url": get_str("LOG_API_URL", "").strip(),
            "log_api_level": get_str("LOG_API_LEVEL", "ERROR"),
            "log_api_timeout_ms": get_int("LOG_API_TIMEOUT_MS", 2000),
            "log_service_name": get_str("LOG_SERVICE_NAME", "perceptual-metrics-service"),
            "log_api_token_configured": bool(get_str("LOG_API_TOKEN", "").strip()),
            "hmac_enabled": get_bool("HMAC_ENABLED", default=False),
            "hmac_secret_configured": bool(get_str("HMAC_SECRET", "").strip()),
            "hmac_allowed_skew_sec": get_int("HMAC_ALLOWED_SKEW_SEC", 300),
            "hmac_require_nonce": get_bool("HMAC_REQUIRE_NONCE", default=True),
            "hmac_nonce_ttl_sec": get_int("HMAC_NONCE_TTL_SEC", 300),
            "git": get_git_metadata().as_dict(),
        }

        validate_redis_job_store_startup(store)
        logger.info("Application startup settings: {}", settings)

        try:
            yield
        finally:
            app.state.job_store = None

    app = FastAPI(
        title="Perceptual Metrics Service",
        version="1.0.0",
        description=(
            "API for LPIPS/DISTS image similarity scoring and LPIPS heatmap generation. "
            "Supports asynchronous comparison jobs API."
        ),
        openapi_tags=[
            {"name": "health", "description": "Service health and readiness."},
            {"name": "compare", "description": "Image comparison endpoints."},
        ],
        lifespan=lifespan,
    )

    app.state.job_store = None

    app.include_router(health_router)
    app.include_router(compare_router)

    @app.get("/metrics", include_in_schema=False)
    async def metrics() -> Response:
        return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)

    if debug:

        @app.exception_handler(Exception)
        async def unhandled_exception_handler(request: Request, exc: Exception):
            logger.exception("Unhandled exception on {} {}", request.method, request.url.path)

            return JSONResponse(
                status_code=500,
                content={
                    "error": type(exc).__name__,
                    "detail": str(exc),
                    "path": request.url.path,
                    "method": request.method,
                },
            )

    return app


app = create_app()
