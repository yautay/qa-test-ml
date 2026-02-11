from fastapi import APIRouter

from app.core.device import resolve_device
from app.core.registry import registry

router = APIRouter()


@router.get("/health")
def health():
    return {"status": "ok", "device": resolve_device(None), "metrics": registry.list()}
