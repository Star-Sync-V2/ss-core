from fastapi import APIRouter, Depends, Query
from typing import Optional, Dict, Any
from ..services.db import get_db
from ..services.scheduler import SchedulerService

router = APIRouter(prefix="/api/v1/schedule", tags=["schedule"])

@router.post("/replan")
def replan(mission_id: Optional[int] = Query(default=None), db=Depends(get_db)) -> Dict[str, Any]:
    return SchedulerService(db).replan(mission_id)

@router.post("/whatif")
def whatif(request_id: int, db=Depends(get_db)) -> Dict[str, Any]:
    return SchedulerService(db).whatif(request_id)
