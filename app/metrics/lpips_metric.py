import io
import torch
import torch.nn.functional as F
import lpips

from app.metrics.base import Metric, MetricResult
from app.schemas.compare import LpipsDistanceConfig, LpipsHeatmapConfig
from app.core.device import resolve_device
from app.core.image_io import load_rgb_pil, pil_to_tensor_minus1_1, match_size, \
    resize_pair_to_max_side
from app.core.heatmap import normalize_0_1, heatmap_red, overlay


class LpipsMetric(Metric):
    name = "lpips"

    def __init__(self):
        self._scalar = {}  # net -> model
        self._spatial = {}  # net -> model(spatial=True)

    def _model_scalar(self, net: str, device: str):
        key = (net, device)
        if key not in self._scalar:
            self._scalar[key] = lpips.LPIPS(net=net).to(device).eval()
        return self._scalar[key]

    def _model_spatial(self, net: str, device: str):
        key = (net, device)
        if key not in self._spatial:
            self._spatial[key] = lpips.LPIPS(net=net, spatial=True).to(device).eval()
        return self._spatial[key]

    def distance(self, ref_path: str, test_path: str, config: LpipsDistanceConfig) -> MetricResult:

        device = resolve_device(config.force_device)
        model = self._model_scalar(config.net, device)

        ref_img = load_rgb_pil(ref_path)
        tst_img = load_rgb_pil(test_path)

        # opcjonalnie: jeśli chcesz mieć max_side także dla skalaru, dodaj do configu
        # i użyj:
        # ref_img, tst_img = resize_pair_to_max_side(ref_img, tst_img, config.max_side)

        ref_img, tst_img = match_size(ref_img, tst_img)

        ref_t = pil_to_tensor_minus1_1(ref_img, device)
        tst_t = pil_to_tensor_minus1_1(tst_img, device)


        with torch.no_grad():
            d = model(ref_t, tst_t)

        return MetricResult(
            value=float(d.squeeze().cpu().item()),
            meta={"metric": self.name, "net": config.net, "device": device},
        )

    def heatmap_png(self, ref_path: str, test_path: str, config: LpipsHeatmapConfig) -> bytes:
        device = resolve_device(config.force_device)  # domyślnie cpu
        model = self._model_spatial(config.net, device)

        ref_img = load_rgb_pil(ref_path)
        tst_img = load_rgb_pil(test_path)

        ref_img, tst_img = resize_pair_to_max_side(ref_img, tst_img, config.max_side)
        ref_img, tst_img = match_size(ref_img, tst_img)

        ref_t = pil_to_tensor_minus1_1(ref_img, device)
        tst_t = pil_to_tensor_minus1_1(tst_img, device)

        H, W = ref_t.shape[2], ref_t.shape[3]

        with torch.no_grad():
            d_map = model(ref_t, tst_t)  # [1,1,h,w] (zwykle mniejsze)

        d_map_up = F.interpolate(d_map, size=(H, W), mode="bilinear", align_corners=False)

        m = d_map_up.squeeze().detach().cpu().numpy()
        m01 = normalize_0_1(m)
        heat = heatmap_red(m01)

        base = tst_img if config.overlay_on == "test" else ref_img
        out = overlay(base, heat, alpha=config.alpha)

        buf = io.BytesIO()
        out.save(buf, format="PNG")
        return buf.getvalue()
