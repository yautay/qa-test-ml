from fastapi import FastAPI
from app.api.routes.health import router as health_router
from app.api.routes.compare import router as compare_router


def create_app() -> FastAPI:
    app = FastAPI(title="Perceptual Metrics Service")
    app.include_router(health_router)
    app.include_router(compare_router)
    return app


app = create_app()
