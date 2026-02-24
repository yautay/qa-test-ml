from typing import Literal

from pydantic import BaseModel, Field

JobMetricName = Literal["lpips", "dists", "both"]
JobStatusName = Literal["queued", "running", "done", "error"]


class HeatmapBaseConfig(BaseModel):
    force_device: Literal["cpu", "cuda"] | None = None
    max_side: int = Field(default=1024, ge=128, le=4096)
    overlay_on: Literal["test", "ref"] = "test"
    alpha: float = Field(default=0.45, ge=0.0, le=1.0)


class DistanceBaseConfig(BaseModel):
    force_device: Literal["cpu", "cuda"] | None = None  # None => auto


class LpipsDistanceConfig(DistanceBaseConfig):
    metric: Literal["lpips"] = "lpips"
    net: Literal["vgg", "alex", "squeeze"] = "vgg"


class LpipsHeatmapConfig(HeatmapBaseConfig):
    metric: Literal["lpips"] = "lpips"
    net: Literal["vgg", "alex", "squeeze"] = "vgg"


class DistsDistanceConfig(DistanceBaseConfig):
    metric: Literal["dists"] = "dists"


class ErrorResponse(BaseModel):
    detail: str


class JobAcceptedResponse(BaseModel):
    job_id: str
    status: Literal["queued"]
    poll_url: str


class JobStatusResponse(BaseModel):
    job_id: str
    pair_id: str
    status: JobStatusName
    metric: JobMetricName
    model: str
    normalize: bool
    lpips: float | None = None
    dists: float | None = None
    timing_ms: int | None = None
    error_message: str | None = None
    error_url: str | None = None
    heatmap_url: str | None = None


class JobsListResponse(BaseModel):
    jobs: list[JobStatusResponse]


class JobErrorResponse(BaseModel):
    job_id: str
    status: Literal["error"]
    error_message: str
    timing_ms: int | None = None
