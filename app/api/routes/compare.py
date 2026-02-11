from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from app.schemas.compare import (
    CompareRequest,
    CompareResponse,
    HeatmapRequest,
)
from app.core.registry import registry

router = APIRouter()


@router.post("/compare", response_model=CompareResponse)
def compare(req: CompareRequest):
    try:
        metric = registry.get(req.config.metric)
        result = metric.distance(req.ref_path, req.test_path, req.config)
        return {"value": result.value, "meta": result.meta}
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=f"File not found: {e}")
    except KeyError:
        raise HTTPException(status_code=400, detail=f"Metric not registered: {req.config.metric}")


@router.post("/compare/heatmap")
def compare_heatmap(req: HeatmapRequest):
    try:
        metric = registry.get(req.config.metric)
        png = metric.heatmap_png(req.ref_path, req.test_path, req.config)
        return Response(content=png, media_type="image/png")
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except NotImplementedError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=f"File not found: {e}")
    except KeyError:
        raise HTTPException(status_code=400, detail=f"Metric not registered: {req.config.metric}")
