# app/routers/mission.py

from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session

from app.services.db import get_db
from app.services.mission import MissionService
from app.models.mission import (
    MissionCreateModel,
    MissionReadModel,
    MissionUpdateModel,
)
from app.services.auth import get_current_user
from app.models.user import UserModel
from app.routers.error import getErrorResponses

router = APIRouter(
    prefix="/mission",
    tags=["Mission"],
)


def require_system_admin(current_user: UserModel = Depends(get_current_user)) -> UserModel:
    if current_user.role != "system_admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only system_admin can perform this action",
        )
    return current_user


@router.post(
    "/",
    summary="Create a new mission",
    response_model=MissionReadModel,
    responses={
        **getErrorResponses(403),
        **getErrorResponses(503),
        **getErrorResponses(500),
    },  # type: ignore[dict-item]
)
def create_mission(
    mission_in: MissionCreateModel,
    db: Session = Depends(get_db),
    current_user: UserModel = Depends(require_system_admin),
):
    return MissionService.create_mission(db, mission_in)


@router.get(
    "/",
    summary="List all missions",
    response_model=List[MissionReadModel],
    responses={**getErrorResponses(503), **getErrorResponses(500)},  # type: ignore[dict-item]
)
def list_missions(
    db: Session = Depends(get_db),
    current_user: UserModel = Depends(get_current_user),
):
    # For now: all roles can list missions; we can tighten later if needed
    return MissionService.get_missions(db)


@router.get(
    "/{mission_id}",
    summary="Get a mission by ID",
    response_model=MissionReadModel,
    responses={
        **getErrorResponses(404),
        **getErrorResponses(503),
        **getErrorResponses(500),
    },  # type: ignore[dict-item]
)
def get_mission(
    mission_id: int,
    db: Session = Depends(get_db),
    current_user: UserModel = Depends(get_current_user),
):
    return MissionService.get_mission(db, mission_id)


@router.patch(
    "/{mission_id}",
    summary="Update a mission",
    response_model=MissionReadModel,
    responses={
        **getErrorResponses(403),
        **getErrorResponses(404),
        **getErrorResponses(503),
        **getErrorResponses(500),
    },  # type: ignore[dict-item]
)
def update_mission(
    mission_id: int,
    mission_in: MissionUpdateModel,
    db: Session = Depends(get_db),
    current_user: UserModel = Depends(require_system_admin),
):
    return MissionService.update_mission(db, mission_id, mission_in)


@router.delete(
    "/{mission_id}",
    summary="Delete a mission",
    responses={
        **getErrorResponses(403),
        **getErrorResponses(404),
        **getErrorResponses(503),
        **getErrorResponses(500),
    },  # type: ignore[dict-item]
)
def delete_mission(
    mission_id: int,
    db: Session = Depends(get_db),
    current_user: UserModel = Depends(require_system_admin),
):
    MissionService.delete_mission(db, mission_id)
    return {"message": "Mission deleted successfully"}
