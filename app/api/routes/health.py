from fastapi import APIRouter
from pydantic import BaseModel

from app.core.build_info import get_git_metadata
from app.core.device import resolve_device
from app.core.registry import registry

router = APIRouter(tags=["health"])


class HealthResponse(BaseModel):
    class GitInfo(BaseModel):
        branch: str
        tag: str
        last_commit: str
        committer: str
        date: str

    status: str
    device: str
    metrics: list[str]
    git: GitInfo


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Service health",
    description="Returns service status, resolved device, available metrics, and git metadata.",
)
def health():
    return {
        "status": "ok",
        "device": resolve_device(None),
        "metrics": registry.list(),
        "git": get_git_metadata().as_dict(),
    }
