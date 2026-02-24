from fastapi import APIRouter, Request
from pydantic import BaseModel

from app.core.build_info import get_git_metadata
from app.core.device import resolve_device
from app.core.registry import registry

router = APIRouter(tags=["health"])


class HealthResponse(BaseModel):
    class JobStoreInfo(BaseModel):
        backend: str
        available: bool

    class GitInfo(BaseModel):
        branch: str
        tag: str
        last_commit: str
        committer: str
        date: str

    status: str
    device: str
    metrics: list[str]
    job_store: JobStoreInfo
    git: GitInfo


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Service health",
    description="Returns service status, resolved device, available metrics, and git metadata.",
)
def health(request: Request):
    store = getattr(request.app.state, "job_store", None)
    backend = "unknown"
    available = False
    if store is not None:
        backend = getattr(store, "backend_name", "unknown")
        available = bool(store.is_available())

    return {
        "status": "ok",
        "device": resolve_device(None),
        "metrics": registry.list(),
        "job_store": {"backend": backend, "available": available},
        "git": get_git_metadata().as_dict(),
    }
