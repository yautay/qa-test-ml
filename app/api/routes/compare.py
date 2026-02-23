import base64
from typing import cast
from uuid import UUID

from fastapi import APIRouter, File, Form, HTTPException, Request, Response, UploadFile, status

from app.core.jobs import CompareJobManager
from app.core.registry import registry
from app.schemas.compare import (
    CompareAllRequest,
    CompareAllResponse,
    DistsCompareRequest,
    DistsCompareResponse,
    DistsDistanceConfig,
    ErrorResponse,
    JobAcceptedResponse,
    JobMetricName,
    JobsListResponse,
    JobStatusResponse,
    LpipsCompareRequest,
    LpipsCompareResponse,
    LpipsDistanceConfig,
    LpipsHeatmapConfig,
)

router = APIRouter(prefix="", tags=["compare"])
IMG_A_FILE = File(..., description="First image file")
IMG_B_FILE = File(..., description="Second image file")


def _encode_png_base64(png: bytes) -> str:
    return base64.b64encode(png).decode("ascii")


@router.post(
    "/compare",
    response_model=CompareAllResponse,
    summary="Compare images with LPIPS and DISTS",
    description="Computes LPIPS scalar, DISTS scalar, and LPIPS heatmap (base64 PNG) in one response.",
    responses={
        200: {"description": "LPIPS + DISTS + LPIPS heatmap"},
        400: {"model": ErrorResponse, "description": "Invalid input or unsupported settings"},
        403: {"model": ErrorResponse, "description": "Path outside IMAGE_BASE_DIR"},
        404: {"model": ErrorResponse, "description": "Input file not found"},
        422: {"description": "Validation error"},
    },
)
def compare(req: CompareAllRequest):
    try:
        lpips_metric = registry.get("lpips")
        dists_metric = registry.get("dists")

        lpips_dist_cfg = LpipsDistanceConfig(
            net=req.config.lpips_net, force_device=req.config.force_device
        )
        lpips_heat_cfg = LpipsHeatmapConfig(
            net=req.config.lpips_net,
            force_device=req.config.force_device,
            max_side=req.config.max_side,
            overlay_on=req.config.overlay_on,
            alpha=req.config.alpha,
        )
        dists_dist_cfg = DistsDistanceConfig(force_device=req.config.force_device)

        lpips_result = lpips_metric.distance(req.ref_path, req.test_path, lpips_dist_cfg)
        dists_result = dists_metric.distance(req.ref_path, req.test_path, dists_dist_cfg)
        lpips_heatmap = lpips_metric.heatmap_png(req.ref_path, req.test_path, lpips_heat_cfg)

        return {
            "lpips": {"value": lpips_result.value, "meta": lpips_result.meta},
            "dists": {"value": dists_result.value, "meta": dists_result.meta},
            "lpips_heatmap_png_base64": _encode_png_base64(lpips_heatmap),
        }
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except NotImplementedError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=f"File not found: {e}") from e
    except KeyError as e:
        raise HTTPException(status_code=400, detail=f"Metric not registered: {e}") from e


def _job_to_status_response(job, request: Request) -> JobStatusResponse:
    heatmap_url = None
    if job.heatmap_png is not None and job.status == "done":
        heatmap_url = str(request.url_for("get_compare_job_heatmap", job_id=job.job_id))

    return JobStatusResponse(
        job_id=job.job_id,
        pair_id=job.pair_id,
        status=job.status,
        metric=job.metric,
        model=job.model,
        normalize=job.normalize,
        lpips=job.lpips,
        dists=job.dists,
        timing_ms=job.timing_ms,
        error_message=job.error_message,
        heatmap_url=heatmap_url,
    )


def _get_jobs_manager(request: Request) -> CompareJobManager:
    manager = getattr(request.app.state, "compare_jobs", None)
    if manager is None:
        raise HTTPException(status_code=503, detail="Jobs manager is not available")
    return manager


@router.post(
    "/v1/compare/jobs",
    response_model=JobAcceptedResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Create compare job",
    description=(
        "Creates an asynchronous comparison job from two binary image uploads (multipart/form-data). "
        "Job status can be polled via the returned poll_url."
    ),
    responses={
        202: {"description": "Job accepted and queued"},
        400: {"model": ErrorResponse, "description": "Invalid input"},
        409: {"model": ErrorResponse, "description": "Duplicate job_id"},
        503: {"model": ErrorResponse, "description": "Jobs manager unavailable"},
    },
)
async def create_compare_job(
    request: Request,
    job_id: str = Form(..., description="UUID string"),
    pair_id: str = Form(..., description="Pair identifier from source dataset"),
    metric: str = Form(..., description='One of: "lpips", "dists", "both"'),
    model: str = Form("alex", description="LPIPS model, e.g. alex/vgg/squeeze"),
    normalize: str = Form("true", description='Boolean string: "true" or "false"'),
    img_a: UploadFile = IMG_A_FILE,
    img_b: UploadFile = IMG_B_FILE,
):
    try:
        UUID(job_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="job_id must be a valid UUID") from exc

    if metric not in {"lpips", "dists", "both"}:
        raise HTTPException(
            status_code=400, detail='metric must be one of: "lpips", "dists", "both"'
        )
    metric_name = cast(JobMetricName, metric)

    normalized_value = normalize.strip().lower()
    if normalized_value not in {"true", "false"}:
        raise HTTPException(status_code=400, detail='normalize must be "true" or "false"')
    normalize_bool = normalized_value == "true"

    img_a_bytes = await img_a.read()
    img_b_bytes = await img_b.read()
    if not img_a_bytes or not img_b_bytes:
        raise HTTPException(status_code=400, detail="img_a and img_b must not be empty")

    manager = _get_jobs_manager(request)
    try:
        await manager.enqueue(
            job_id=job_id,
            pair_id=pair_id,
            metric=metric_name,
            model=model,
            normalize=normalize_bool,
            img_a_bytes=img_a_bytes,
            img_b_bytes=img_b_bytes,
            img_a_name=img_a.filename or "img_a.png",
            img_b_name=img_b.filename or "img_b.png",
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    return {
        "job_id": job_id,
        "status": "queued",
        "poll_url": str(request.url_for("get_compare_job_status", job_id=job_id)),
    }


@router.get(
    "/v1/compare/jobs/{job_id}",
    response_model=JobStatusResponse,
    summary="Get compare job status",
    description="Returns current status for a single async comparison job.",
    responses={
        200: {"description": "Job status"},
        404: {"model": ErrorResponse, "description": "Job not found"},
        503: {"model": ErrorResponse, "description": "Jobs manager unavailable"},
    },
)
async def get_compare_job_status(request: Request, job_id: str):
    manager = _get_jobs_manager(request)
    job = await manager.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Job not found: {job_id}")
    return _job_to_status_response(job, request)


@router.get(
    "/v1/compare/jobs",
    response_model=JobsListResponse,
    summary="List compare jobs",
    description="Returns statuses of all async comparison jobs currently stored in memory.",
    responses={
        200: {"description": "List of job statuses"},
        503: {"model": ErrorResponse, "description": "Jobs manager unavailable"},
    },
)
async def list_compare_jobs(request: Request):
    manager = _get_jobs_manager(request)
    jobs = await manager.list()
    return {"jobs": [_job_to_status_response(job, request) for job in jobs]}


@router.get(
    "/v1/compare/jobs/{job_id}/heatmap",
    name="get_compare_job_heatmap",
    summary="Download LPIPS heatmap",
    description="Returns heatmap PNG for a completed job that includes LPIPS metric.",
    responses={
        200: {
            "description": "PNG heatmap",
            "content": {"image/png": {}},
        },
        404: {"model": ErrorResponse, "description": "Job not found or heatmap unavailable"},
        503: {"model": ErrorResponse, "description": "Jobs manager unavailable"},
    },
)
async def get_compare_job_heatmap(request: Request, job_id: str):
    manager = _get_jobs_manager(request)
    job = await manager.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Job not found: {job_id}")
    if job.status != "done" or job.heatmap_png is None:
        raise HTTPException(status_code=404, detail=f"Heatmap not available for job: {job_id}")
    return Response(content=job.heatmap_png, media_type="image/png")


@router.post(
    "/compare/lpips",
    response_model=LpipsCompareResponse,
    summary="Compare images with LPIPS",
    description="Computes LPIPS scalar score and LPIPS heatmap as base64-encoded PNG.",
    responses={
        200: {"description": "LPIPS score and heatmap"},
        400: {"model": ErrorResponse, "description": "Invalid input or unsupported settings"},
        403: {"model": ErrorResponse, "description": "Path outside IMAGE_BASE_DIR"},
        404: {"model": ErrorResponse, "description": "Input file not found"},
        422: {"description": "Validation error"},
    },
)
def compare_lpips(req: LpipsCompareRequest):
    try:
        lpips_metric = registry.get("lpips")

        lpips_dist_cfg = LpipsDistanceConfig(
            net=req.config.net, force_device=req.config.force_device
        )
        lpips_heat_cfg = LpipsHeatmapConfig(
            net=req.config.net,
            force_device=req.config.force_device,
            max_side=req.config.max_side,
            overlay_on=req.config.overlay_on,
            alpha=req.config.alpha,
        )

        lpips_result = lpips_metric.distance(req.ref_path, req.test_path, lpips_dist_cfg)
        lpips_heatmap = lpips_metric.heatmap_png(req.ref_path, req.test_path, lpips_heat_cfg)

        return {
            "lpips": {"value": lpips_result.value, "meta": lpips_result.meta},
            "lpips_heatmap_png_base64": _encode_png_base64(lpips_heatmap),
        }
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except NotImplementedError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=f"File not found: {e}") from e
    except KeyError as e:
        raise HTTPException(status_code=400, detail=f"Metric not registered: {e}") from e


@router.post(
    "/compare/dists",
    response_model=DistsCompareResponse,
    summary="Compare images with DISTS",
    description="Computes DISTS scalar score for a pair of images.",
    responses={
        200: {"description": "DISTS score"},
        400: {"model": ErrorResponse, "description": "Invalid input or unsupported settings"},
        403: {"model": ErrorResponse, "description": "Path outside IMAGE_BASE_DIR"},
        404: {"model": ErrorResponse, "description": "Input file not found"},
        422: {"description": "Validation error"},
    },
)
def compare_dists(req: DistsCompareRequest):
    try:
        dists_metric = registry.get("dists")
        dists_dist_cfg = DistsDistanceConfig(force_device=req.config.force_device)
        dists_result = dists_metric.distance(req.ref_path, req.test_path, dists_dist_cfg)

        return {"dists": {"value": dists_result.value, "meta": dists_result.meta}}
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=f"File not found: {e}") from e
    except KeyError as e:
        raise HTTPException(status_code=400, detail=f"Metric not registered: {e}") from e
