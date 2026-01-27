import os
from typing import Literal

import torch
import lpips
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from PIL import Image
import torchvision.transforms as T

app = FastAPI(title="LPIPS Service")

# Cache modeli: jeden per architektura
_models = {}


def get_device() -> str:
    return "cuda" if torch.cuda.is_available() else "cpu"


def get_model(net: str):
    if net not in _models:
        device = get_device()
        _models[net] = lpips.LPIPS(net=net).to(device).eval()
    return _models[net]


def load_rgb_tensor(path: str, device: str):
    if not os.path.exists(path):
        raise FileNotFoundError(path)
    img = Image.open(path).convert("RGB")
    # LPIPS zakłada tensor w zakresie [-1, 1] (typowa praktyka)
    t = T.Compose([
        T.ToTensor(),
        T.Lambda(lambda x: x * 2.0 - 1.0),
    ])
    return t(img).unsqueeze(0).to(device)


class LpipsRequest(BaseModel):
    ref_path: str
    test_path: str
    net: Literal["vgg", "alex", "squeeze"] = "vgg"


class LpipsResponse(BaseModel):
    lpips: float
    net: str
    device: str


@app.get("/health")
def health():
    return {"status": "ok", "device": get_device(), "loaded_models": list(_models.keys())}


@app.post("/lpips", response_model=LpipsResponse)
def lpips_distance(req: LpipsRequest):
    device = get_device()
    try:
        model = get_model(req.net)
        ref = load_rgb_tensor(req.ref_path, device)
        tst = load_rgb_tensor(req.test_path, device)
        with torch.no_grad():
            d = model(ref, tst)
        return {"lpips": float(d.squeeze().cpu().item()), "net": req.net, "device": device}
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=f"File not found: {e}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
