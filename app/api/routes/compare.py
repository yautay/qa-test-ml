from fastapi import APIRouter, HTTPException, Response
from app.schemas.compare import CompareRequest, CompareResponse, HeatmapRequest
from app.core.device import get_device
from app.core.registry import registry

router = APIRouter()


@router.post("/compare", response_model=CompareResponse)
def compare(req: CompareRequest):
    device = get_device()
    try:
        metric = registry.get(req.metric)

        kwargs = {}
        if req.metric == "lpips":
            # jeśli net nie podany, metryka ustawi default
            if req.net is not None:
                kwargs["net"] = req.net

        result = metric.distance(
            ref_path=req.ref_path,
            test_path=req.test_path,
            device=device,
            **kwargs
        )
        return {"value": result.value, "meta": result.meta}

    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=f"File not found: {e}")
    except KeyError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/compare/heatmap")
def compare_heatmap(req: HeatmapRequest):
    device = get_device()
    try:
        metric = registry.get(req.metric)
        kwargs = {
            "alpha": req.alpha,
            "overlay_on": req.overlay_on,
        }
        if req.metric == "lpips" and req.net is not None:
            kwargs["net"] = req.net

        png_bytes = metric.heatmap_png(
            ref_path=req.ref_path,
            test_path=req.test_path,
            device=device,
            **kwargs
        )
        return Response(content=png_bytes, media_type="image/png")

    except NotImplementedError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=f"File not found: {e}")
    except KeyError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
