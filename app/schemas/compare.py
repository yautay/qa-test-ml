from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

MetricName = Literal["lpips", "dists"]
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


class DistsHeatmapConfig(HeatmapBaseConfig):
    metric: Literal["dists"] = "dists"


class LpipsCompareConfig(HeatmapBaseConfig):
    net: Literal["vgg", "alex", "squeeze"] = "vgg"


class DistsCompareConfig(DistanceBaseConfig):
    pass


class CompareAllConfig(HeatmapBaseConfig):
    lpips_net: Literal["vgg", "alex", "squeeze"] = "vgg"


class CompareAllRequest(BaseModel):
    ref_path: str
    test_path: str
    config: CompareAllConfig = Field(default_factory=CompareAllConfig)

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "ref_path": "tests/assets/ref_1.png",
                "test_path": "tests/assets/test_1.png",
                "config": {
                    "lpips_net": "vgg",
                    "force_device": "cpu",
                    "max_side": 1024,
                    "overlay_on": "test",
                    "alpha": 0.45,
                },
            }
        }
    )


class LpipsCompareRequest(BaseModel):
    ref_path: str
    test_path: str
    config: LpipsCompareConfig = Field(default_factory=LpipsCompareConfig)

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "ref_path": "tests/assets/ref_1.png",
                "test_path": "tests/assets/test_1.png",
                "config": {
                    "net": "alex",
                    "force_device": "cpu",
                    "max_side": 1024,
                    "overlay_on": "test",
                    "alpha": 0.45,
                },
            }
        }
    )


class DistsCompareRequest(BaseModel):
    ref_path: str
    test_path: str
    config: DistsCompareConfig = Field(default_factory=DistsCompareConfig)

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "ref_path": "tests/assets/ref_1.png",
                "test_path": "tests/assets/test_1.png",
                "config": {"force_device": "cpu"},
            }
        }
    )


class MetricScoreResponse(BaseModel):
    value: float
    meta: dict[str, Any]


class LpipsCompareResponse(BaseModel):
    lpips: MetricScoreResponse
    lpips_heatmap_png_base64: str


class CompareAllResponse(BaseModel):
    lpips: MetricScoreResponse
    dists: MetricScoreResponse
    lpips_heatmap_png_base64: str


class DistsCompareResponse(BaseModel):
    dists: MetricScoreResponse


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
    heatmap_url: str | None = None


class JobsListResponse(BaseModel):
    jobs: list[JobStatusResponse]
