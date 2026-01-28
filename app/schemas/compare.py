from typing import Literal, Optional
from pydantic import BaseModel, Field

MetricName = Literal["lpips"]  # dopiszesz "dists" później


class CompareRequest(BaseModel):
    metric: MetricName = "lpips"
    ref_path: str
    test_path: str
    net: Optional[Literal["vgg", "alex", "squeeze"]] = None  # tylko dla LPIPS


class CompareResponse(BaseModel):
    value: float
    meta: dict


class HeatmapRequest(BaseModel):
    metric: MetricName = "lpips"
    ref_path: str
    test_path: str
    net: Optional[Literal["vgg", "alex", "squeeze"]] = None
    overlay_on: Literal["test", "ref"] = "test"
    alpha: float = Field(default=0.45, ge=0.0, le=1.0)
