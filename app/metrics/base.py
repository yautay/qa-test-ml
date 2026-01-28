from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Dict


@dataclass(frozen=True)
class MetricResult:
    value: float
    meta: Dict[str, Any]


class Metric(ABC):
    name: str  # np. "lpips", "dists"

    @abstractmethod
    def cache_key(self, **kwargs) -> str:
        ...

    @abstractmethod
    def distance(self, ref_path: str, test_path: str, device: str, **kwargs) -> MetricResult:
        ...

    def heatmap_png(
            self,
            ref_path: str,
            test_path: str,
            device: str,
            **kwargs
    ) -> bytes:
        raise NotImplementedError(f"Heatmap not supported for metric '{self.name}'")
