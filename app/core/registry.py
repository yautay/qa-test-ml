from app.metrics.lpips_metric import LpipsMetric
from app.metrics.base import Metric


class MetricRegistry:
    def __init__(self):
        self._metrics = {}

    def register(self, metric: Metric) -> None:
        self._metrics[metric.name] = metric

    def get(self, name: str) -> Metric:
        if name not in self._metrics:
            raise KeyError(f"Metric not found: {name}")
        return self._metrics[name]

    def list_names(self):
        return sorted(self._metrics.keys())


registry = MetricRegistry()
registry.register(LpipsMetric())
# registry.register(DistsMetric())  # włączysz jak wdrożysz
