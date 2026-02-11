from typing import Annotated, Literal, Union
from pydantic import BaseModel, Field

MetricName = Literal["lpips", "dists"]


class HeatmapBaseConfig(BaseModel):
    force_device: Literal["cpu", "cuda"] = "cpu"
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


DistanceConfig = Annotated[
    Union[LpipsDistanceConfig, DistsDistanceConfig],
    Field(discriminator="metric")
]

HeatmapConfig = Annotated[
    Union[LpipsHeatmapConfig, DistsHeatmapConfig],
    Field(discriminator="metric")
]


class CompareRequest(BaseModel):
    ref_path: str
    test_path: str
    config: DistanceConfig


class CompareResponse(BaseModel):
    value: float
    meta: dict


class HeatmapRequest(BaseModel):
    ref_path: str
    test_path: str
    config: HeatmapConfig
