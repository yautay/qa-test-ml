import os
from PIL import Image
import torchvision.transforms as T


def resize_pair_to_max_side(ref: Image.Image, tst: Image.Image, max_side: int) -> tuple[Image.Image, Image.Image]:
    w1, h1 = ref.size
    w2, h2 = tst.size
    longest = max(w1, h1, w2, h2)
    if longest <= max_side:
        return ref, tst

    scale = max_side / float(longest)

    def _resize(img: Image.Image) -> Image.Image:
        w, h = img.size
        new_w = max(1, int(round(w * scale)))
        new_h = max(1, int(round(h * scale)))
        return img.resize((new_w, new_h), resample=Image.BILINEAR)

    return _resize(ref), _resize(tst)


def match_size(ref: Image.Image, tst: Image.Image) -> tuple[Image.Image, Image.Image]:
    # Dopasuj test do rozmiaru referencji (gwarancja identycznych tensorów)
    if ref.size == tst.size:
        return ref, tst
    return ref, tst.resize(ref.size, resample=Image.BILINEAR)


def ensure_exists(path: str) -> None:
    if not os.path.exists(path):
        raise FileNotFoundError(path)


def load_rgb_pil(path: str) -> Image.Image:
    ensure_exists(path)
    return Image.open(path).convert("RGB")


def resize_to_max_side(img: Image.Image, max_side: int) -> Image.Image:
    w, h = img.size
    longest = max(w, h)
    if longest <= max_side:
        return img
    scale = max_side / float(longest)
    new_w = max(1, int(round(w * scale)))
    new_h = max(1, int(round(h * scale)))
    return img.resize((new_w, new_h), resample=Image.BILINEAR)


_pil_to_tensor_minus1_1 = T.Compose([
    T.ToTensor(),
    T.Lambda(lambda x: x * 2.0 - 1.0),
])


def pil_to_tensor_minus1_1(img: Image.Image, device: str):
    return _pil_to_tensor_minus1_1(img).unsqueeze(0).to(device)
