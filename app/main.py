import logging
import os

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.api.routes.compare import router as compare_router
from app.api.routes.health import router as health_router

log = logging.getLogger("uvicorn.error")


def create_app() -> FastAPI:
    app = FastAPI(title="Perceptual Metrics Service")

    app.include_router(health_router)
    app.include_router(compare_router)

    debug = os.getenv("API_DEBUG", "1") == "1"

    if debug:

        @app.exception_handler(Exception)
        async def unhandled_exception_handler(request: Request, exc: Exception):
            # Loguje pełny traceback do logów uvicorn
            log.exception("Unhandled exception on %s %s", request.method, request.url.path)

            # Zwraca czytelny JSON do klienta
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
