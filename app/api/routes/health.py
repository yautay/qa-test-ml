from fastapi import APIRouter
from pydantic import BaseModel

from app.core.device import resolve_device
from app.core.registry import registry

router = APIRouter(tags=["health"])


class HealthResponse(BaseModel):
    status: str
    device: str
    metrics: list[str]


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Service health",
    description="Returns service status, resolved compute device, and available metrics.",
)
def health():
    return {"status": "ok", "device": resolve_device(None), "metrics": registry.list()}
