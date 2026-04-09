from __future__ import annotations

from pathlib import Path

from celery import Celery
from celery.signals import worker_init, worker_process_shutdown, worker_ready
from prometheus_client import REGISTRY, CollectorRegistry, multiprocess, start_http_server

from app.core.config import get_bool, get_int, get_str


def _queue_names() -> tuple[str, str]:
    cpu = get_str("COMPARE_QUEUE_CPU", "compare-cpu").strip() or "compare-cpu"
    gpu = get_str("COMPARE_QUEUE_GPU", "compare-gpu").strip() or "compare-gpu"
    return cpu, gpu


def create_celery_app() -> Celery:
    broker = get_str("CELERY_BROKER_URL", get_str("REDIS_URL", "redis://127.0.0.1:6379/0"))
    backend = get_str("CELERY_RESULT_BACKEND", broker)
    queue_cpu, queue_gpu = _queue_names()

    app = Celery("ai_corner", broker=broker, backend=backend, include=["app.tasks.compare_tasks"])
    app.conf.update(
        task_default_queue=queue_cpu,
        task_routes={
            "app.tasks.compare_tasks.process_compare_job": {"queue": queue_cpu},
        },
        task_serializer="json",
        accept_content=["json"],
        result_serializer="json",
        timezone="UTC",
        enable_utc=True,
        task_always_eager=get_bool("CELERY_TASK_ALWAYS_EAGER", default=False),
        task_eager_propagates=get_bool("CELERY_TASK_EAGER_PROPAGATES", default=False),
        task_time_limit=get_int("CELERY_TASK_TIME_LIMIT", 300),
        task_soft_time_limit=get_int("CELERY_TASK_SOFT_TIME_LIMIT", 240),
        worker_prefetch_multiplier=get_int("CELERY_WORKER_PREFETCH_MULTIPLIER", 1),
        task_acks_late=get_bool("CELERY_ACKS_LATE", default=True),
    )
    app.conf.task_create_missing_queues = True
    return app


celery_app = create_celery_app()


def _prometheus_enabled() -> bool:
    return get_bool("PROMETHEUS_WORKER_ENABLED", default=False)


def _prometheus_registry() -> CollectorRegistry:
    multiproc_dir = get_str("PROMETHEUS_MULTIPROC_DIR", "").strip()
    if not multiproc_dir:
        return REGISTRY

    registry = CollectorRegistry()
    multiprocess.MultiProcessCollector(registry)
    return registry


@worker_init.connect
def _worker_init_prometheus(**_: object) -> None:
    if not _prometheus_enabled():
        return

    multiproc_dir = get_str("PROMETHEUS_MULTIPROC_DIR", "").strip()
    if not multiproc_dir:
        return

    dir_path = Path(multiproc_dir)
    dir_path.mkdir(parents=True, exist_ok=True)
    for db_file in dir_path.glob("*.db"):
        db_file.unlink(missing_ok=True)


@worker_ready.connect
def _worker_ready_prometheus(**_: object) -> None:
    if not _prometheus_enabled():
        return

    port = get_int("PROMETHEUS_WORKER_PORT", 9101)
    addr = get_str("PROMETHEUS_WORKER_ADDR", "0.0.0.0").strip() or "0.0.0.0"  # nosec B104

    registry = _prometheus_registry()
    start_http_server(port, addr=addr, registry=registry)


@worker_process_shutdown.connect
def _worker_process_shutdown_prometheus(pid: int | None = None, **_: object) -> None:
    if not _prometheus_enabled():
        return

    if pid is None:
        return

    if not get_str("PROMETHEUS_MULTIPROC_DIR", "").strip():
        return

    multiprocess.mark_process_dead(pid)
