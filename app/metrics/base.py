from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class MetricResult:
    value: float
    meta: dict[str, Any]


class Metric(ABC):
    name: str

    @abstractmethod
    def distance(self, ref_path: str, test_path: str, config) -> MetricResult: ...

    def heatmap_png(self, ref_path: str, test_path: str, config) -> bytes:
        raise NotImplementedError(f"Heatmap not supported for metric '{self.name}'")
