import numpy as np
from PIL import Image

_RESAMPLE_BILINEAR = getattr(Image, "Resampling", Image).BILINEAR


def normalize_0_1(m: np.ndarray) -> np.ndarray:
    """
    Normalize a 2D array to [0, 1].
    """
    m = m.astype(np.float32)
    m = m - float(m.min())
    denom = float(m.max()) + 1e-8
    return m / denom


def heatmap_red(m01: np.ndarray) -> np.ndarray:
    """
    Create a simple red heatmap from a 2D normalized map.
    m01: HxW float array in [0, 1]
    returns: HxWx3 uint8 RGB heatmap
    """
    r = (m01 * 255.0).clip(0, 255).astype(np.uint8)
    g = np.zeros_like(r, dtype=np.uint8)
    b = np.zeros_like(r, dtype=np.uint8)
    return np.stack([r, g, b], axis=-1)


def overlay(base_rgb: Image.Image, heat_rgb: np.ndarray, alpha: float) -> Image.Image:
    """
    Alpha-blend heatmap onto base image.
    base_rgb: PIL.Image in RGB
    heat_rgb: HxWx3 uint8
    alpha: 0..1
    returns: PIL.Image RGB
    """
    if not (0.0 <= float(alpha) <= 1.0):
        raise ValueError("alpha must be in [0, 1]")

    base = np.array(base_rgb.convert("RGB"), dtype=np.float32)

    if heat_rgb.ndim != 3 or heat_rgb.shape[2] != 3:
        raise ValueError("heat_rgb must be HxWx3")

    # Ensure same spatial size; resize heatmap if needed
    if (base.shape[1], base.shape[0]) != (heat_rgb.shape[1], heat_rgb.shape[0]):
        heat_img = Image.fromarray(heat_rgb, mode="RGB").resize(
            (base.shape[1], base.shape[0]), resample=_RESAMPLE_BILINEAR
        )
        heat = np.array(heat_img, dtype=np.float32)
    else:
        heat = heat_rgb.astype(np.float32)

    out = base * (1.0 - alpha) + heat * alpha
    out = np.clip(out, 0, 255).astype(np.uint8)
    return Image.fromarray(out, mode="RGB")
