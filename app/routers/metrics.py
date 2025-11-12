from fastapi import APIRouter
router = APIRouter(prefix="/api/v1/metrics", tags=["metrics"])

@router.get("")
def get_metrics():
    # You can wire real aggregation later; keep a stub working for Friday.
    return {"fulfillment_rate": 0.0, "utilization": {}, "utilization_stddev": 0.0, "avg_replan_ms": 0}
