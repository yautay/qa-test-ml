from __future__ import annotations

import asyncio
import os
import tempfile
import time
from contextlib import suppress
from dataclasses import dataclass
from typing import Literal, cast

from loguru import logger

from app.core.config import get_str
from app.core.registry import registry
from app.schemas.compare import (
    DistsDistanceConfig,
    JobMetricName,
    JobStatusName,
    LpipsDistanceConfig,
    LpipsHeatmapConfig,
)


@dataclass
class JobRecord:
    job_id: str
    pair_id: str
    metric: JobMetricName
    model: str
    normalize: bool
    img_a_path: str
    img_b_path: str
    img_a_name: str
    img_b_name: str
    status: JobStatusName = "queued"
    lpips: float | None = None
    dists: float | None = None
    timing_ms: int | None = None
    error_message: str | None = None
    heatmap_png: bytes | None = None


class CompareJobManager:
    def __init__(self, workers: int = 2, queue_maxsize: int = 0):
        self._workers_count = max(1, workers)
        self._queue: asyncio.Queue[str] = asyncio.Queue(maxsize=max(0, queue_maxsize))
        self._jobs: dict[str, JobRecord] = {}
        self._lock = asyncio.Lock()
        self._workers: list[asyncio.Task[None]] = []

    async def start(self) -> None:
        for _ in range(self._workers_count):
            self._workers.append(asyncio.create_task(self._worker_loop()))

    async def stop(self) -> None:
        for worker in self._workers:
            worker.cancel()
        for worker in self._workers:
            with suppress(asyncio.CancelledError):
                await worker
        self._workers.clear()

    async def enqueue(
        self,
        *,
        job_id: str,
        pair_id: str,
        metric: JobMetricName,
        model: str,
        normalize: bool,
        img_a_bytes: bytes,
        img_b_bytes: bytes,
        img_a_name: str,
        img_b_name: str,
    ) -> JobRecord:
        if not self._workers:
            await self.start()

        async with self._lock:
            if job_id in self._jobs:
                raise ValueError(f"Job already exists: {job_id}")

            img_a_path = self._store_temp_image(img_a_bytes, img_a_name)
            img_b_path = self._store_temp_image(img_b_bytes, img_b_name)
            job = JobRecord(
                job_id=job_id,
                pair_id=pair_id,
                metric=metric,
                model=model,
                normalize=normalize,
                img_a_path=img_a_path,
                img_b_path=img_b_path,
                img_a_name=img_a_name,
                img_b_name=img_b_name,
            )
            self._jobs[job_id] = job
            await self._queue.put(job_id)
            logger.bind(
                class_name="CompareJobManager",
                method_name="enqueue",
                job_id=job_id,
                pair_id=pair_id,
                metric=metric,
                model=model,
                normalize=normalize,
                img_a_name=img_a_name,
                img_b_name=img_b_name,
            ).debug("Compare job queued")
            return job

    async def get(self, job_id: str) -> JobRecord | None:
        async with self._lock:
            return self._jobs.get(job_id)

    async def list(self) -> list[JobRecord]:
        async with self._lock:
            return list(self._jobs.values())

    async def _worker_loop(self) -> None:
        while True:
            job_id = await self._queue.get()
            try:
                await self._run_job(job_id)
            finally:
                self._queue.task_done()

    async def _run_job(self, job_id: str) -> None:
        async with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return
            job.status = "running"
        logger.bind(
            class_name="CompareJobManager",
            method_name="_run_job",
            job_id=job.job_id,
            pair_id=job.pair_id,
            metric=job.metric,
            model=job.model,
            normalize=job.normalize,
            img_a_name=job.img_a_name,
            img_b_name=job.img_b_name,
        ).debug("Compare job started")

        started = time.perf_counter()
        try:
            await asyncio.to_thread(self._process_sync, job)
            elapsed_ms = int((time.perf_counter() - started) * 1000)
            async with self._lock:
                saved = self._jobs[job_id]
                saved.status = "done"
                saved.timing_ms = elapsed_ms
            logger.bind(
                class_name="CompareJobManager",
                method_name="_run_job",
                job_id=job.job_id,
                pair_id=job.pair_id,
                metric=job.metric,
                model=job.model,
                normalize=job.normalize,
                img_a_name=job.img_a_name,
                img_b_name=job.img_b_name,
                timing_ms=elapsed_ms,
                lpips=job.lpips,
                dists=job.dists,
                has_heatmap=job.heatmap_png is not None,
            ).debug("Compare job finished")
        except Exception as exc:
            elapsed_ms = int((time.perf_counter() - started) * 1000)
            logger.bind(
                class_name="CompareJobManager",
                method_name="_run_job",
                job_id=job.job_id,
                pair_id=job.pair_id,
                metric=job.metric,
                model=job.model,
                normalize=job.normalize,
                img_a_name=job.img_a_name,
                img_b_name=job.img_b_name,
                img_a_path=job.img_a_path,
                img_b_path=job.img_b_path,
                timing_ms=elapsed_ms,
            ).exception("Compare job failed")
            async with self._lock:
                saved = self._jobs[job_id]
                saved.status = "error"
                saved.error_message = str(exc)
                saved.timing_ms = elapsed_ms
        finally:
            self._cleanup_temp_inputs(job)

    def _process_sync(self, job: JobRecord) -> None:
        if job.metric in {"lpips", "both"}:
            lpips_metric = registry.get("lpips")
            lpips_net = cast(Literal["vgg", "alex", "squeeze"], job.model)
            lpips_dist_cfg = LpipsDistanceConfig(net=lpips_net)
            lpips_heat_cfg = LpipsHeatmapConfig(net=lpips_net)
            lpips_result = lpips_metric.distance(job.img_a_path, job.img_b_path, lpips_dist_cfg)
            heatmap_png = lpips_metric.heatmap_png(job.img_a_path, job.img_b_path, lpips_heat_cfg)
            job.lpips = lpips_result.value
            job.heatmap_png = heatmap_png

        if job.metric in {"dists", "both"}:
            dists_metric = registry.get("dists")
            dists_dist_cfg = DistsDistanceConfig()
            dists_result = dists_metric.distance(job.img_a_path, job.img_b_path, dists_dist_cfg)
            job.dists = dists_result.value

    @staticmethod
    def _cleanup_temp_inputs(job: JobRecord) -> None:
        for path in (job.img_a_path, job.img_b_path):
            with suppress(FileNotFoundError):
                os.remove(path)

    @staticmethod
    def _store_temp_image(content: bytes, original_name: str) -> str:
        suffix = os.path.splitext(original_name)[1] or ".png"
        base_dir = os.path.realpath(os.path.abspath(get_str("IMAGE_BASE_DIR", ".")))
        fd, path = tempfile.mkstemp(prefix="compare_job_", suffix=suffix, dir=base_dir)
        with os.fdopen(fd, "wb") as f:
            f.write(content)
        return path
