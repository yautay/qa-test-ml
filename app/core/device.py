import torch


def auto_device() -> str:
    return "cuda" if torch.cuda.is_available() else "cpu"


def resolve_device(force_device: str | None) -> str:
    if force_device in ("cpu", "cuda"):
        return force_device
    return auto_device()
