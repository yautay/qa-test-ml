try:
    import piq
except ImportError:  # pragma: no cover
    piq = None
import torch

from app.core.device import resolve_device
from app.core.image_io import load_rgb_pil, match_size, pil_to_tensor_0_1
from app.metrics.base import Metric, MetricResult
from app.schemas.compare import DistsDistanceConfig


class DistsMetric(Metric):
    name = "dists"

    def __init__(self):
        self._models: dict[str, torch.nn.Module] = {}

    def _model(self, device: str) -> torch.nn.Module:
        if piq is None:
            raise RuntimeError("DISTS requires 'piq' package. Install it to enable this metric.")
        if device not in self._models:
            # PIQ DISTS expects NCHW tensors in [0, 1]
            self._models[device] = piq.DISTS().to(device).eval()
        return self._models[device]

    def distance(self, ref_path: str, test_path: str, config: DistsDistanceConfig) -> MetricResult:
        device = resolve_device(config.force_device)
        model = self._model(device)

        ref_img = load_rgb_pil(ref_path)
        tst_img = load_rgb_pil(test_path)
        ref_img, tst_img = match_size(ref_img, tst_img)

        ref_t = pil_to_tensor_0_1(ref_img, device)
        tst_t = pil_to_tensor_0_1(tst_img, device)

        with torch.no_grad():
            d = model(ref_t, tst_t)

        return MetricResult(
            value=float(d.squeeze().detach().cpu().item()),
            meta={"metric": self.name, "device": device},
        )
