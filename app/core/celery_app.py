from __future__ import annotations

from celery import Celery

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
