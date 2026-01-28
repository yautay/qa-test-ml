from fastapi import APIRouter
from app.core.device import get_device
from app.core.registry import registry

router = APIRouter()


@router.get("/health")
def health():
    return {"status": "ok", "device": get_device(), "metrics": registry.list_names()}
