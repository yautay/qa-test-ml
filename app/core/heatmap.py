import numpy as np
from PIL import Image


def normalize_0_1(m: np.ndarray) -> np.ndarray:
    m = m.astype(np.float32)
    m = m - float(m.min())
    denom = float(m.max()) + 1e-8
    return m / denom


def heatmap_red(m01: np.ndarray) -> np.ndarray:
    """
    m01: HxW float in [0,1]
    returns: HxWx3 uint8 heatmap (prosty: czerwony kanał)
    """
    r = (m01 * 255.0).clip(0, 255).astype(np.uint8)
    g = np.zeros_like(r, dtype=np.uint8)
    b = np.zeros_like(r, dtype=np.uint8)
    return np.stack([r, g, b], axis=-1)


def overlay(base_rgb: Image.Image, heat_rgb: np.ndarray, alpha: float) -> Image.Image:
    """
    base_rgb: PIL RGB
    heat_rgb: HxWx3 uint8
    alpha: 0..1
    """
    base = np.array(base_rgb.convert("RGB"), dtype=np.float32)
    heat = heat_rgb.astype(np.float32)

    out = base * (1.0 - alpha) + heat * alpha
    out = np.clip(out, 0, 255).astype(np.uint8)
    return Image.fromarray(out, mode="RGB")
