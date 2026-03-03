import base64
import hashlib
import io
from typing import cast
from uuid import UUID

from fastapi import APIRouter, File, Form, HTTPException, Request, Response, UploadFile, status
from loguru import logger
from PIL import Image, UnidentifiedImageError
from PIL.Image import DecompressionBombError

from app.core.celery_app import celery_app
from app.core.config import get_bool, get_int, get_str
from app.core.execution import queue_names, select_queue_for_job
from app.core.hmac_auth import verify_hmac_request
from app.core.job_store import JobState, now_ms
from app.core.metrics import jobs_submitted_total, rejected_requests_total
from app.core.rate_limit import rate_limiter
from app.schemas.compare import (
    ErrorResponse,
    JobAcceptedResponse,
    JobErrorResponse,
    JobMetricName,
    JobsListResponse,
    JobStatusResponse,
)

router = APIRouter(prefix="", tags=["compare"])
IMG_A_FILE = File(..., description="First image file")
IMG_B_FILE = File(..., description="Second image file")


def _reject(request: Request, *, endpoint: str, status_code: int, detail: str, reason: str) -> None:
    rejected_requests_total.labels(endpoint=endpoint, reason=reason, status_code=str(status_code)).inc()
    logger.bind(
        class_name="CompareAPI",
        endpoint=endpoint,
        reason=reason,
        status_code=status_code,
        path=request.url.path,
        method=request.method,
    ).warning("Request rejected: {}", detail)
    raise HTTPException(status_code=status_code, detail=detail)


def _client_key(request: Request) -> str:
    client = request.client
    if client is None:
        return "unknown"
    return client.host or "unknown"


def _rate_limit_request(request: Request, *, endpoint: str, bucket: str) -> None:
    if not get_bool("COMPARE_RATE_LIMIT_ENABLED", default=False):
        return

    if bucket == "create":
        limit = get_int("COMPARE_RATE_LIMIT_CREATE_LIMIT", 60)
        window_sec = get_int("COMPARE_RATE_LIMIT_CREATE_WINDOW_SEC", 60)
    else:
        limit = get_int("COMPARE_RATE_LIMIT_READ_LIMIT", 240)
        window_sec = get_int("COMPARE_RATE_LIMIT_READ_WINDOW_SEC", 60)

    key = f"{bucket}:{_client_key(request)}"
    if not rate_limiter.allow(key, limit=limit, window_sec=window_sec):
        _reject(
            request,
            endpoint=endpoint,
            status_code=429,
            detail="Rate limit exceeded. Please retry later.",
            reason="rate_limited",
        )


def _allowed_image_formats() -> set[str]:
    raw = get_str("COMPARE_ALLOWED_IMAGE_FORMATS", "png,jpeg,webp")
    allowed = {item.strip().upper() for item in raw.split(",") if item.strip()}
    if not allowed:
        return {"PNG", "JPEG", "WEBP"}
    return allowed


def _validate_image_bytes(request: Request, *, endpoint: str, content: bytes, field_name: str) -> None:
    if not content:
        _reject(
            request,
            endpoint=endpoint,
            status_code=400,
            detail=f"{field_name} must not be empty",
            reason="empty_upload",
        )

    max_file_bytes = get_int("COMPARE_MAX_FILE_SIZE_BYTES", 10 * 1024 * 1024)
    if max_file_bytes > 0 and len(content) > max_file_bytes:
        _reject(
            request,
            endpoint=endpoint,
            status_code=413,
            detail=f"{field_name} exceeds maximum allowed size",
            reason="file_too_large",
        )

    max_side = get_int("COMPARE_MAX_IMAGE_SIDE", 8192)
    max_pixels = get_int("COMPARE_MAX_IMAGE_PIXELS", 40_000_000)
    allowed_formats = _allowed_image_formats()
    image_format = ""
    width = 0
    height = 0

    try:
        with Image.open(io.BytesIO(content)) as image:
            image_format = (image.format or "").upper()
            width, height = image.size
    except DecompressionBombError:
        _reject(
            request,
            endpoint=endpoint,
            status_code=413,
            detail=f"{field_name} image dimensions are too large",
            reason="image_too_large",
        )
    except UnidentifiedImageError:
        _reject(
            request,
            endpoint=endpoint,
            status_code=415,
            detail=f"{field_name} is not a supported image file",
            reason="unsupported_media_type",
        )
    except OSError:
        _reject(
            request,
            endpoint=endpoint,
            status_code=400,
            detail=f"{field_name} is not a valid image",
            reason="invalid_image",
        )

    if image_format not in allowed_formats:
        _reject(
            request,
            endpoint=endpoint,
            status_code=415,
            detail=f"{field_name} has unsupported format: {image_format or 'unknown'}",
            reason="unsupported_media_type",
        )

    if max_side > 0 and (width > max_side or height > max_side):
        _reject(
            request,
            endpoint=endpoint,
            status_code=413,
            detail=f"{field_name} exceeds max image side",
            reason="image_too_large",
        )

    if max_pixels > 0 and width * height > max_pixels:
        _reject(
            request,
            endpoint=endpoint,
            status_code=413,
            detail=f"{field_name} exceeds max image pixel count",
            reason="image_too_large",
        )


def _job_to_status_response(job: JobState, request: Request) -> JobStatusResponse:
    heatmap_url = None
    error_url = None
    if job.has_heatmap and job.status == "done":
        heatmap_url = str(request.url_for("get_compare_job_heatmap", job_id=job.job_id))
    if job.status == "error":
        error_url = str(request.url_for("get_compare_job_error", job_id=job.job_id))

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
        error_url=error_url,
        heatmap_url=heatmap_url,
    )


def _get_job_store(request: Request):
    store = getattr(request.app.state, "job_store", None)
    if store is None:
        logger.bind(class_name="CompareAPI", method_name="_get_job_store").error("Job store is not available")
        raise HTTPException(status_code=503, detail="Job store is not available")
    return store


def _select_queue() -> str:
    return select_queue_for_job()


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
        413: {"model": ErrorResponse, "description": "Payload/image too large"},
        415: {"model": ErrorResponse, "description": "Unsupported media type"},
        429: {"model": ErrorResponse, "description": "Rate limit exceeded"},
        503: {"model": ErrorResponse, "description": "Job store unavailable"},
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
    endpoint = "create_compare_job"
    _rate_limit_request(request, endpoint=endpoint, bucket="create")

    max_total_bytes = get_int("COMPARE_MAX_TOTAL_UPLOAD_BYTES", 20 * 1024 * 1024)
    content_length_header = request.headers.get("content-length", "").strip()
    if max_total_bytes > 0 and content_length_header:
        try:
            content_length = int(content_length_header)
        except ValueError:
            content_length = -1
        if content_length > max_total_bytes:
            _reject(
                request,
                endpoint=endpoint,
                status_code=413,
                detail="Request payload exceeds maximum allowed size",
                reason="payload_too_large",
            )

    try:
        UUID(job_id)
    except ValueError as exc:
        logger.bind(class_name="CompareAPI", method_name="create_compare_job", job_id=job_id).warning(
            "Invalid job_id format"
        )
        raise HTTPException(status_code=400, detail="job_id must be a valid UUID") from exc

    if metric not in {"lpips", "dists", "both"}:
        raise HTTPException(status_code=400, detail='metric must be one of: "lpips", "dists", "both"')
    metric_name = cast(JobMetricName, metric)

    normalized_value = normalize.strip().lower()
    if normalized_value not in {"true", "false"}:
        raise HTTPException(status_code=400, detail='normalize must be "true" or "false"')
    normalize_bool = normalized_value == "true"

    img_a_bytes = await img_a.read()
    img_b_bytes = await img_b.read()
    if max_total_bytes > 0 and (len(img_a_bytes) + len(img_b_bytes)) > max_total_bytes:
        _reject(
            request,
            endpoint=endpoint,
            status_code=413,
            detail="Combined upload size exceeds maximum allowed limit",
            reason="payload_too_large",
        )

    _validate_image_bytes(request, endpoint=endpoint, content=img_a_bytes, field_name="img_a")
    _validate_image_bytes(request, endpoint=endpoint, content=img_b_bytes, field_name="img_b")

    verify_hmac_request(
        request,
        fields={
            "job_id": job_id,
            "pair_id": pair_id,
            "metric": metric_name,
            "model": model,
            "normalize": normalized_value,
            "img_a_sha256": hashlib.sha256(img_a_bytes).hexdigest(),
            "img_b_sha256": hashlib.sha256(img_b_bytes).hexdigest(),
        },
    )

    store = _get_job_store(request)
    created_at_ms = now_ms()
    try:
        store.create_job(
            JobState(
                job_id=job_id,
                pair_id=pair_id,
                metric=metric_name,
                model=model,
                normalize=normalize_bool,
                img_a_name=img_a.filename or "img_a.png",
                img_b_name=img_b.filename or "img_b.png",
                status="queued",
                created_at_ms=created_at_ms,
            )
        )
    except ValueError as exc:
        logger.bind(class_name="CompareAPI", method_name="create_compare_job", job_id=job_id).warning(
            "Duplicate compare job id"
        )
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    jobs_submitted_total.labels(metric=metric_name).inc()
    _, gpu_queue = queue_names()
    queue_name = _select_queue()
    force_device = "cuda" if queue_name == gpu_queue else "cpu"
    try:
        celery_app.signature(
            "app.tasks.compare_tasks.process_compare_job",
            kwargs={
                "job_id": job_id,
                "pair_id": pair_id,
                "metric": metric_name,
                "model": model,
                "normalize": normalize_bool,
                "img_a_name": img_a.filename or "img_a.png",
                "img_b_name": img_b.filename or "img_b.png",
                "img_a_b64": base64.b64encode(img_a_bytes).decode("ascii"),
                "img_b_b64": base64.b64encode(img_b_bytes).decode("ascii"),
                "force_device": force_device,
                "fallback_from_gpu": False,
            },
            queue=queue_name,
            task_id=job_id,
        ).apply_async()
    except Exception as exc:
        logger.bind(
            class_name="CompareAPI",
            method_name="create_compare_job",
            job_id=job_id,
            pair_id=pair_id,
            metric=metric_name,
            queue=queue_name,
        ).opt(exception=exc).exception("Failed to enqueue compare job")
        store.update_job(
            job_id,
            status="error",
            error_message="Failed to enqueue compare job. Please retry.",
        )
        raise HTTPException(status_code=503, detail="Failed to enqueue compare job") from exc
    logger.bind(
        class_name="CompareAPI",
        method_name="create_compare_job",
        job_id=job_id,
        pair_id=pair_id,
        metric=metric_name,
        model=model,
        normalize=normalize_bool,
        queue=queue_name,
        force_device=force_device,
    ).debug("Compare job queued")

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
        429: {"model": ErrorResponse, "description": "Rate limit exceeded"},
        503: {"model": ErrorResponse, "description": "Job store unavailable"},
    },
)
async def get_compare_job_status(request: Request, job_id: str):
    _rate_limit_request(request, endpoint="get_compare_job_status", bucket="read")
    verify_hmac_request(request)
    store = _get_job_store(request)
    job = store.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Job not found: {job_id}")
    return _job_to_status_response(job, request)


@router.get(
    "/v1/compare/jobs",
    response_model=JobsListResponse,
    summary="List compare jobs",
    description="Returns statuses of all async comparison jobs stored in shared job store.",
    responses={
        200: {"description": "List of job statuses"},
        429: {"model": ErrorResponse, "description": "Rate limit exceeded"},
        503: {"model": ErrorResponse, "description": "Job store unavailable"},
    },
)
async def list_compare_jobs(request: Request):
    _rate_limit_request(request, endpoint="list_compare_jobs", bucket="read")
    verify_hmac_request(request)
    store = _get_job_store(request)
    jobs = store.list_jobs()
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
        429: {"model": ErrorResponse, "description": "Rate limit exceeded"},
        503: {"model": ErrorResponse, "description": "Job store unavailable"},
    },
)
async def get_compare_job_heatmap(request: Request, job_id: str):
    _rate_limit_request(request, endpoint="get_compare_job_heatmap", bucket="read")
    verify_hmac_request(request)
    store = _get_job_store(request)
    job = store.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Job not found: {job_id}")
    if job.status != "done":
        raise HTTPException(status_code=404, detail=f"Heatmap not available for job: {job_id}")
    heatmap_png = store.get_heatmap(job_id)
    if heatmap_png is None:
        raise HTTPException(status_code=404, detail=f"Heatmap not available for job: {job_id}")
    return Response(content=heatmap_png, media_type="image/png")


@router.get(
    "/v1/compare/jobs/{job_id}/error",
    response_model=JobErrorResponse,
    name="get_compare_job_error",
    summary="Get compare job error details",
    description="Returns error details for a failed async comparison job.",
    responses={
        200: {"description": "Job error details"},
        404: {"model": ErrorResponse, "description": "Job not found"},
        409: {"model": ErrorResponse, "description": "Job is not in error state"},
        429: {"model": ErrorResponse, "description": "Rate limit exceeded"},
        503: {"model": ErrorResponse, "description": "Job store unavailable"},
    },
)
async def get_compare_job_error(request: Request, job_id: str):
    _rate_limit_request(request, endpoint="get_compare_job_error", bucket="read")
    verify_hmac_request(request)
    store = _get_job_store(request)
    job = store.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Job not found: {job_id}")
    if job.status != "error":
        raise HTTPException(status_code=409, detail=f"Job is not in error state: {job_id}")

    return {
        "job_id": job.job_id,
        "status": "error",
        "error_message": job.error_message or "Unknown compare job error",
        "timing_ms": job.timing_ms,
    }
