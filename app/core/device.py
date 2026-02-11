import torch


def auto_device() -> str:
    return "cuda" if torch.cuda.is_available() else "cpu"


def resolve_device(force_device: str | None) -> str:
    if force_device == "cpu":
        return "cpu"
    if force_device == "cuda":
        if not torch.cuda.is_available():
            raise ValueError("CUDA requested but not available on this host")
        return "cuda"
    return auto_device()
