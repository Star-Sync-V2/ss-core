# app/routers/schedule.py

from datetime import datetime
from typing import Optional, Dict, Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlmodel import Session

from app.services.db import get_db
from app.services.scheduler import SchedulerService
from app.services.auth import get_current_user
from app.models.user import UserModel

# NOTE: if main.py already has prefix="/api/v1", use prefix="/schedule" here
router = APIRouter(prefix="/api/v1/schedule", tags=["schedule"])


class ScheduleComputeRequest(BaseModel):
    windowStart: datetime = Field(
        description="Start of scheduling horizon (UTC)", examples=["2025-12-02T00:00:00Z"]
    )
    windowEnd: datetime = Field(
        description="End of scheduling horizon (UTC)", examples=["2025-12-02T06:00:00Z"]
    )
    missionId: Optional[int] = Field(
        default=None,
        description="Optional mission ID; if omitted, RBAC determines which missions are visible",
    )


@router.post(
    "/compute",
    summary="Compute an antenna schedule for RF + Contact requests in the given window.",
    responses={
        400: {"description": "Bad input window or parameters"},
        403: {"description": "Forbidden (RBAC)"},
        500: {"description": "Internal error while computing schedule"},
    },
)
def compute_schedule(
    body: ScheduleComputeRequest,
    db: Session = Depends(get_db),
    current_user: UserModel = Depends(get_current_user),
) -> Dict[str, Any]:
    """
    RBAC:
    - RequestService.get_all_requests handles system vs mission roles.
    - missionId in the body further filters results; if you pass a missionId
      the current user cannot see, you simply get an empty schedule.
    """
    window_start = body.windowStart
    window_end = body.windowEnd

    # 🚦 validate the window so 0-length / inverted ranges don't blow up Skyfield / metrics
    if window_end <= window_start:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="windowEnd must be strictly greater than windowStart",
        )

    try:
        scheduler = SchedulerService(db=db, current_user=current_user)
        return scheduler.compute_schedule(
            window_start=window_start,
            window_end=window_end,
            mission_id=body.missionId,
        )

    except HTTPException:
        # propagate explicit 4xx/5xx from inside the scheduler
        raise
    except Exception as e:
        # catch-all so we never leak raw tracebacks to the client
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error while computing schedule: {e}",
        )
