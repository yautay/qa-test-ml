from typing import Any, Literal

from pydantic import BaseModel, Field

MetricName = Literal["lpips", "dists"]


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


class LpipsCompareRequest(BaseModel):
    ref_path: str
    test_path: str
    config: LpipsCompareConfig = Field(default_factory=LpipsCompareConfig)


class DistsCompareRequest(BaseModel):
    ref_path: str
    test_path: str
    config: DistsCompareConfig = Field(default_factory=DistsCompareConfig)


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
