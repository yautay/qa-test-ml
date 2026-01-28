import os
from PIL import Image
import torchvision.transforms as T


def ensure_exists(path: str) -> None:
    if not os.path.exists(path):
        raise FileNotFoundError(path)


_to_tensor_minus1_1 = T.Compose([T.ToTensor(), T.Lambda(lambda x: x * 2.0 - 1.0),])


def load_rgb_tensor_minus1_1(path: str, device: str):
    ensure_exists(path)
    img = Image.open(path).convert("RGB")
    return _to_tensor_minus1_1(img).unsqueeze(0).to(device)


def load_rgb_pil(path: str) -> Image.Image:
    ensure_exists(path)
    return Image.open(path).convert("RGB")
