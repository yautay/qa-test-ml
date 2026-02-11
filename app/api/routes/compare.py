import base64

from fastapi import APIRouter, HTTPException

from app.core.registry import registry
from app.schemas.compare import (
    CompareAllRequest,
    CompareAllResponse,
    DistsCompareRequest,
    DistsCompareResponse,
    DistsDistanceConfig,
    LpipsCompareRequest,
    LpipsCompareResponse,
    LpipsDistanceConfig,
    LpipsHeatmapConfig,
)

router = APIRouter()


def _encode_png_base64(png: bytes) -> str:
    return base64.b64encode(png).decode("ascii")


@router.post("/compare", response_model=CompareAllResponse)
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


@router.post("/compare/lpips", response_model=LpipsCompareResponse)
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


@router.post("/compare/dists", response_model=DistsCompareResponse)
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
