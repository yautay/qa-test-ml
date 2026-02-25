from __future__ import annotations

from typing import Any

from loguru import logger

from app.core.celery_app import celery_app
from app.core.config import get_bool, get_str


def queue_names() -> tuple[str, str]:
    cpu_queue = get_str("COMPARE_QUEUE_CPU", "compare-cpu").strip() or "compare-cpu"
    gpu_queue = get_str("COMPARE_QUEUE_GPU", "compare-gpu").strip() or "compare-gpu"
    return cpu_queue, gpu_queue


def execution_device_mode() -> str:
    mode = get_str("COMPARE_EXECUTION_DEVICE", "auto").strip().lower()
    if mode in {"cpu", "gpu", "auto"}:
        return mode
    logger.bind(class_name="Execution", method_name="execution_device_mode").warning(
        "Invalid COMPARE_EXECUTION_DEVICE='{}'; falling back to 'auto'",
        mode,
    )
    return "auto"


def gpu_queue_enabled() -> bool:
    return get_bool("ENABLE_GPU_QUEUE", default=False)


def select_queue_for_job() -> str:
    cpu_queue, gpu_queue = queue_names()
    mode = execution_device_mode()

    if mode == "cpu" or not gpu_queue_enabled():
        return cpu_queue

    return gpu_queue


def gpu_worker_available(timeout_sec: float = 0.35) -> bool:
    if not gpu_queue_enabled():
        return False

    _, gpu_queue = queue_names()
    try:
        inspect = celery_app.control.inspect(timeout=timeout_sec)
        queues = inspect.active_queues() if inspect is not None else None
        if not queues:
            return False

        for worker_queues in queues.values():
            if not isinstance(worker_queues, list):
                continue
            for queue in worker_queues:
                if isinstance(queue, dict) and queue.get("name") == gpu_queue:
                    return True
        return False
    except Exception as exc:
        logger.bind(class_name="Execution", method_name="gpu_worker_available").opt(exception=exc).warning(
            "Failed to check GPU worker availability"
        )
        return False
