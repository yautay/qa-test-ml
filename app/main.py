import os

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from loguru import logger

from app.api.routes.compare import router as compare_router
from app.api.routes.health import router as health_router
from app.core.config import get_bool, get_int
from app.core.jobs import CompareJobManager
from app.core.logging import configure_logging


def _read_job_runtime_settings() -> tuple[int, int]:
    workers = get_int("COMPARE_JOB_WORKERS", 2)
    queue_maxsize = get_int("QUEUE_MAXSIZE", 0)

    if workers < 1:
        logger.warning("Invalid COMPARE_JOB_WORKERS={} ; using 1", workers)
        workers = 1

    cpu_count = os.cpu_count() or 1
    max_workers = max(1, cpu_count * 4)
    if workers > max_workers:
        logger.warning(
            "COMPARE_JOB_WORKERS={} too high for host (max={}) ; capping", workers, max_workers
        )
        workers = max_workers

    if queue_maxsize < 0:
        logger.warning("Invalid QUEUE_MAXSIZE={} ; using 0", queue_maxsize)
        queue_maxsize = 0

    return workers, queue_maxsize


def create_app() -> FastAPI:
    configure_logging()
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
    )

    app.include_router(health_router)
    app.include_router(compare_router)

    jobs_workers, queue_maxsize = _read_job_runtime_settings()
    jobs_manager = CompareJobManager(workers=jobs_workers, queue_maxsize=queue_maxsize)
    app.state.compare_jobs = jobs_manager

    @app.on_event("startup")
    async def _startup_jobs() -> None:
        await jobs_manager.start()

    @app.on_event("shutdown")
    async def _shutdown_jobs() -> None:
        await jobs_manager.stop()

    debug = get_bool("API_DEBUG", default=True)

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
