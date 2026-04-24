from __future__ import annotations

from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from celery import Celery
from celery.signals import worker_init, worker_process_shutdown, worker_ready
from prometheus_client import REGISTRY, CollectorRegistry, multiprocess, start_http_server

from app.core.config import get_bool, get_int, get_redis_connection_settings, get_str


def _queue_names() -> tuple[str, str]:
    cpu = get_str("COMPARE_QUEUE_CPU", "compare-cpu").strip() or "compare-cpu"
    gpu = get_str("COMPARE_QUEUE_GPU", "compare-gpu").strip() or "compare-gpu"
    return cpu, gpu


def _is_redis_broker_url(url: str) -> bool:
    scheme = urlsplit(url).scheme.strip().lower()
    return scheme in {"redis", "rediss"}


def create_celery_app() -> Celery:
    broker = get_str("CELERY_BROKER_URL", "").strip() or get_redis_connection_settings().url
    backend = get_str("CELERY_RESULT_BACKEND", broker)
    queue_cpu, queue_gpu = _queue_names()
    redis_prefix = get_str("REDIS_PREFIX", "pms").strip() or "pms"

    broker_transport_options: dict[str, object] = {}
    result_backend_transport_options: dict[str, object] = {}

    if _is_redis_broker_url(broker):
        broker_transport_options["global_keyprefix"] = f"{redis_prefix}:"

    if _is_redis_broker_url(backend):
        result_backend_transport_options["global_keyprefix"] = f"{redis_prefix}:"

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
        broker_transport_options=broker_transport_options,
        result_backend_transport_options=result_backend_transport_options,
    )
    app.conf.task_create_missing_queues = True
    return app


class _LazyCeleryApp:
    def __init__(self) -> None:
        self._app: Celery | None = None

    def _get_app(self) -> Celery:
        if self._app is None:
            self._app = create_celery_app()
        return self._app

    def clear(self) -> None:
        self._app = None

    def __getattr__(self, name: str) -> Any:
        return getattr(self._get_app(), name)


celery_app = _LazyCeleryApp()


def _clear_celery_app_cache() -> None:
    celery_app.clear()


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
