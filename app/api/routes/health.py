from fastapi import APIRouter, Request
from pydantic import BaseModel

from app.core.build_info import get_git_metadata
from app.core.execution import execution_device_mode, gpu_queue_enabled, gpu_worker_available
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

    class GpuInfo(BaseModel):
        enabled: bool
        mode: str
        available: bool
        fallback_to_cpu: bool

    status: str
    metrics: list[str]
    job_store: JobStoreInfo
    git: GitInfo
    gpu: GpuInfo


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Service health",
    description="Returns service status, available metrics, and runtime metadata.",
)
def health(request: Request):
    store = getattr(request.app.state, "job_store", None)
    backend = "unknown"
    store_available = False
    if store is not None:
        backend = getattr(store, "backend_name", "unknown")
        store_available = bool(store.is_available())

    mode = execution_device_mode()
    enabled = gpu_queue_enabled()
    gpu_available = gpu_worker_available() if enabled and mode != "cpu" else False

    return {
        "status": "ok",
        "metrics": registry.list(),
        "job_store": {"backend": backend, "available": store_available},
        "git": get_git_metadata().as_dict(),
        "gpu": {
            "enabled": enabled,
            "mode": mode,
            "available": gpu_available,
            "fallback_to_cpu": bool(enabled and mode != "cpu" and not gpu_available),
        },
    }
