from app.metrics.base import Metric, MetricResult


class DistsMetric(Metric):
    name = "dists"

    def __init__(self):
        self._models = {}

    def cache_key(self, **kwargs) -> str:
        return "dists:default"

    def distance(self, ref_path: str, test_path: str, device: str, **kwargs) -> MetricResult:
        raise NotImplementedError("DISTS not implemented yet")
