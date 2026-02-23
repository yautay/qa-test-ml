import os

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from loguru import logger

from app.api.routes.compare import router as compare_router
from app.api.routes.health import router as health_router
from app.core.jobs import CompareJobManager
from app.core.logging import configure_logging


def create_app() -> FastAPI:
    configure_logging()
    app = FastAPI(
        title="Perceptual Metrics Service",
        version="1.0.0",
        description=(
            "API for LPIPS/DISTS image similarity scoring and LPIPS heatmap generation. "
            "Supports synchronous compare endpoints and asynchronous jobs API."
        ),
        openapi_tags=[
            {"name": "health", "description": "Service health and readiness."},
            {"name": "compare", "description": "Image comparison endpoints."},
        ],
    )

    app.include_router(health_router)
    app.include_router(compare_router)

    jobs_manager = CompareJobManager()
    app.state.compare_jobs = jobs_manager

    @app.on_event("startup")
    async def _startup_jobs() -> None:
        await jobs_manager.start()

    @app.on_event("shutdown")
    async def _shutdown_jobs() -> None:
        await jobs_manager.stop()

    debug = os.getenv("API_DEBUG", "1") == "1"

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
