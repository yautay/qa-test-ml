from app.metrics.dists_metric import DistsMetric
from app.metrics.lpips_metric import LpipsMetric


class MetricRegistry:
    def __init__(self):
        self._m = {}

    def register(self, metric):
        self._m[metric.name] = metric

    def get(self, name: str):
        return self._m[name]

    def list(self):
        return sorted(self._m.keys())


registry = MetricRegistry()
registry.register(LpipsMetric())
registry.register(DistsMetric())
