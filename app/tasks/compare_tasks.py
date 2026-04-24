from __future__ import annotations

import base64
import os
import tempfile
import time
from contextlib import suppress
from typing import Literal, cast

from loguru import logger

from app.core.celery_app import celery_app
from app.core.config import get_str
from app.core.execution import queue_names
from app.core.image_io import resolve_input_path
from app.core.job_store import get_job_store
from app.core.metrics import (
    job_duration_seconds,
    jobs_failed_total,
    jobs_finished_total,
    jobs_inflight,
    jobs_started_total,
)
from app.core.registry import registry
from app.schemas.compare import (
    DistsDistanceConfig,
    JobMetricName,
    LpipsDistanceConfig,
    LpipsHeatmapConfig,
)

_HEATMAP_ERROR_MESSAGE = "LPIPS heatmap generation failed. Please verify image dimensions/content and retry."
_GPU_ERROR_TOKENS = (
    "cuda",
    "cudnn",
    "cublas",
    "nvidia",
    "not compiled with cuda",
    "out of memory",
)


def _store_temp_image(content: bytes, original_name: str) -> str:
    suffix = os.path.splitext(original_name)[1] or ".png"
    configured_tmp_dir = get_str("COMPARE_TMP_DIR", ".compare_tmp").strip() or ".compare_tmp"
    try:
        base_dir = resolve_input_path(configured_tmp_dir)
    except PermissionError as exc:
        raise RuntimeError(
            "COMPARE_TMP_DIR must point inside IMAGE_BASE_DIR " f"(got: {configured_tmp_dir!r})"
        ) from exc
    os.makedirs(base_dir, exist_ok=True)
    fd, path = tempfile.mkstemp(prefix="compare_job_", suffix=suffix, dir=base_dir)
    with os.fdopen(fd, "wb") as f:
        f.write(content)
    return path


def _cleanup(paths: list[str]) -> None:
    for path in paths:
        with suppress(FileNotFoundError):
            os.remove(path)


def _is_gpu_failure(exc: Exception) -> bool:
    text = str(exc).strip().lower()
    if not text:
        return False
    return any(token in text for token in _GPU_ERROR_TOKENS)


@celery_app.task(name="app.tasks.compare_tasks.process_compare_job")
def process_compare_job(
    *,
    job_id: str,
    pair_id: str,
    metric: JobMetricName,
    model: str,
    normalize: bool,
    img_a_name: str,
    img_b_name: str,
    img_a_b64: str,
    img_b_b64: str,
    force_device: Literal["cpu", "cuda"] | None = None,
    fallback_from_gpu: bool = False,
) -> None:
    store = get_job_store()

    jobs_started_total.labels(metric=metric).inc()
    jobs_inflight.inc()
    started = time.perf_counter()

    store.update_job(job_id, status="running")

    img_a_path = ""
    img_b_path = ""
    img_a_bytes = base64.b64decode(img_a_b64)
    img_b_bytes = base64.b64decode(img_b_b64)
    img_a_path = _store_temp_image(img_a_bytes, img_a_name)
    img_b_path = _store_temp_image(img_b_bytes, img_b_name)

    final_status = "error"
    observe_duration = True
    try:
        if metric in {"lpips", "both"}:
            lpips_metric = registry.get("lpips")
            lpips_net = cast(Literal["vgg", "alex", "squeeze"], model)
            lpips_dist_cfg = LpipsDistanceConfig(net=lpips_net, force_device=force_device)
            lpips_heat_cfg = LpipsHeatmapConfig(net=lpips_net, force_device=force_device)
            lpips_result = lpips_metric.distance(img_a_path, img_b_path, lpips_dist_cfg)
            heatmap_png = None
            try:
                heatmap_png = lpips_metric.heatmap_png(img_a_path, img_b_path, lpips_heat_cfg)
            except Exception as exc:
                logger.bind(
                    class_name="CompareTask",
                    method_name="process_compare_job",
                    job_id=job_id,
                    pair_id=pair_id,
                    metric=metric,
                    model=model,
                    normalize=normalize,
                    img_a_name=img_a_name,
                    img_b_name=img_b_name,
                    img_a_path=img_a_path,
                    img_b_path=img_b_path,
                ).opt(exception=exc).critical("LPIPS heatmap generation failed; marking job as error")
                raise RuntimeError(_HEATMAP_ERROR_MESSAGE) from exc

            store.update_job(job_id, lpips=lpips_result.value)
            if heatmap_png is not None:
                store.set_heatmap(job_id, heatmap_png)

        if metric in {"dists", "both"}:
            dists_metric = registry.get("dists")
            dists_cfg = DistsDistanceConfig(force_device=force_device)
            dists_result = dists_metric.distance(img_a_path, img_b_path, dists_cfg)
            store.update_job(job_id, dists=dists_result.value)

        elapsed_ms = int((time.perf_counter() - started) * 1000)
        store.update_job(job_id, status="done", timing_ms=elapsed_ms)
        jobs_finished_total.labels(metric=metric).inc()
        final_status = "done"
    except Exception as exc:
        should_fallback = force_device == "cuda" and not fallback_from_gpu and _is_gpu_failure(exc)
        if should_fallback:
            cpu_queue, _ = queue_names()
            logger.bind(
                class_name="CompareTask",
                method_name="process_compare_job",
                job_id=job_id,
                pair_id=pair_id,
                metric=metric,
                model=model,
                normalize=normalize,
                img_a_name=img_a_name,
                img_b_name=img_b_name,
                fallback_queue=cpu_queue,
            ).opt(exception=exc).warning("GPU execution failed; retrying job on CPU queue")
            store.update_job(job_id, status="queued", error_message=None)
            celery_app.signature(
                "app.tasks.compare_tasks.process_compare_job",
                kwargs={
                    "job_id": job_id,
                    "pair_id": pair_id,
                    "metric": metric,
                    "model": model,
                    "normalize": normalize,
                    "img_a_name": img_a_name,
                    "img_b_name": img_b_name,
                    "img_a_b64": img_a_b64,
                    "img_b_b64": img_b_b64,
                    "force_device": "cpu",
                    "fallback_from_gpu": True,
                },
                queue=cpu_queue,
            ).apply_async()
            final_status = "queued"
            observe_duration = False
            return

        elapsed_ms = int((time.perf_counter() - started) * 1000)
        logger.bind(
            class_name="CompareTask",
            method_name="process_compare_job",
            job_id=job_id,
            pair_id=pair_id,
            metric=metric,
            model=model,
            normalize=normalize,
            img_a_name=img_a_name,
            img_b_name=img_b_name,
            img_a_path=img_a_path,
            img_b_path=img_b_path,
            timing_ms=elapsed_ms,
        ).opt(exception=exc).exception("Compare task failed")
        store.update_job(job_id, status="error", timing_ms=elapsed_ms, error_message=str(exc))
        jobs_failed_total.labels(metric=metric).inc()
        raise
    finally:
        jobs_inflight.dec()
        if observe_duration:
            job_duration_seconds.labels(metric=metric, status=final_status).observe(
                max(0.0, time.perf_counter() - started)
            )
        _cleanup([path for path in (img_a_path, img_b_path) if path])
