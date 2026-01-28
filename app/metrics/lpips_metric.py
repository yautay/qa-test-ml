from typing import Literal, TypeAlias
import io

import torch
import torch.nn.functional as F
import lpips
from PIL import Image

from app.metrics.base import Metric, MetricResult
from app.core.image_io import load_rgb_tensor_minus1_1, load_rgb_pil
from app.core.heatmap import normalize_0_1, heatmap_red, overlay

LpipsNet: TypeAlias = Literal["vgg", "alex", "squeeze"]
OverlayOn: TypeAlias = Literal["test", "ref"]


class LpipsMetric(Metric):
    name = "lpips"

    def __init__(self):
        self._models_scalar = {}  # net -> lpips model (spatial=False)
        self._models_spatial = {}  # net -> lpips model (spatial=True)

    def cache_key(self, **kwargs) -> str:
        net: str = kwargs.get("net", "vgg")
        spatial: bool = bool(kwargs.get("spatial", False))
        return f"lpips:{net}:{'spatial' if spatial else 'scalar'}"

    def _get_model(self, net: LpipsNet, device: str):
        if net not in self._models_scalar:
            self._models_scalar[net] = lpips.LPIPS(net=net).to(device).eval()
        return self._models_scalar[net]

    def _get_model_spatial(self, net: LpipsNet, device: str):
        if net not in self._models_spatial:
            self._models_spatial[net] = lpips.LPIPS(net=net, spatial=True).to(device).eval()
        return self._models_spatial[net]

    def distance(self, ref_path: str, test_path: str, device: str, **kwargs) -> MetricResult:
        net: LpipsNet = kwargs.get("net", "vgg")
        model = self._get_model(net, device)
        ref = load_rgb_tensor_minus1_1(ref_path, device)
        tst = load_rgb_tensor_minus1_1(test_path, device)

        with torch.no_grad():
            d = model(ref, tst)

        return MetricResult(
            value=float(d.squeeze().cpu().item()),
            meta={"metric": self.name, "net": net, "device": device},
        )

    def heatmap_png(
            self,
            ref_path: str,
            test_path: str,
            device: str,
            **kwargs
    ) -> bytes:
        net: LpipsNet = kwargs.get("net", "vgg")
        alpha: float = float(kwargs.get("alpha", 0.45))
        overlay_on: OverlayOn = kwargs.get("overlay_on", "test")

        if overlay_on not in ("test", "ref"):
            raise ValueError("overlay_on must be 'test' or 'ref'")

        # model spatial
        model = self._get_model_spatial(net, device)

        # tensory [-1,1]
        ref_t = load_rgb_tensor_minus1_1(ref_path, device)
        tst_t = load_rgb_tensor_minus1_1(test_path, device)

        H = ref_t.shape[2]
        W = ref_t.shape[3]

        with torch.no_grad():
            d_map = model(ref_t, tst_t)  # [1,1,h,w]

        # upscale do HxW
        d_map_up = F.interpolate(d_map, size=(H, W), mode="bilinear", align_corners=False)

        # do numpy HxW
        m = d_map_up.squeeze().detach().cpu().numpy()
        m01 = normalize_0_1(m)
        heat = heatmap_red(m01)  # HxWx3

        # baza do overlay
        base_img: Image.Image = load_rgb_pil(test_path if overlay_on == "test" else ref_path)
        if base_img.size != (W, H):
            base_img = base_img.resize((W, H))

        out = overlay(base_img, heat, alpha=alpha)

        buf = io.BytesIO()
        out.save(buf, format="PNG")
        return buf.getvalue()
