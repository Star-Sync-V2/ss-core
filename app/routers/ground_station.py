from fastapi import APIRouter, Depends
from typing import List
from sqlmodel import Session

from app.models.ground_station import GroundStationModel, GroundStationUpdateModel
from app.services.ground_station import GroundStationService, GroundStationCreateModel
from app.services.db import get_db
from app.routers.error import getErrorResponses

from app.services.auth import get_current_user
from app.models.user import UserModel
from app.services.permissions import require_system_admin

router = APIRouter(prefix="/gs", tags=["Ground Station"])


# POST /api/v1/gs
@router.post(
    "/",
    summary="Create a new ground station",
    response_model=GroundStationModel,
    response_description="Created ground station object",
    responses={
        **getErrorResponses(403),
        **getErrorResponses(503),
        **getErrorResponses(500),
    },  # type: ignore[dict-item]
)
def create_ground_station(
    request: GroundStationCreateModel,
    db: Session = Depends(get_db),
    current_user: UserModel = Depends(get_current_user),
):
    # 🔒 only system_admin can create GS
    require_system_admin(current_user)
    return GroundStationService.create_ground_station(db, request)


# PATCH /api/v1/gs/{gs_id}
@router.patch(
    "/{gs_id}",
    summary="Update a ground station",
    response_model=GroundStationModel,
    response_description="Updated ground station object",
    responses={
        **getErrorResponses(403),
        **getErrorResponses(404),
        **getErrorResponses(503),
        **getErrorResponses(500),
    },  # type: ignore[dict-item]
)
def update_ground_station(
    gs_id: int,
    request: GroundStationUpdateModel,
    db: Session = Depends(get_db),
    current_user: UserModel = Depends(get_current_user),
):
    # 🔒 only system_admin can update GS
    require_system_admin(current_user)
    return GroundStationService.update_ground_station(db, gs_id, request)


# GET /api/v1/gs
@router.get(
    "/",
    summary="Get a list of all ground stations",
    response_model=List[GroundStationModel],
    response_description="List of ground station objects",
    responses={**getErrorResponses(503), **getErrorResponses(500)},  # type: ignore[dict-item]
)
def get_ground_stations(
    db: Session = Depends(get_db),
    current_user: UserModel = Depends(get_current_user),
):
    # any authenticated user can read (for now)
    return GroundStationService.get_ground_stations(db)


# GET /api/v1/gs/{gs_id}
@router.get(
    "/{gs_id}",
    summary="Get a ground station by id",
    response_model=GroundStationModel,
    response_description="Specific ground station object",
    responses={
        **getErrorResponses(404),
        **getErrorResponses(503),
        **getErrorResponses(500),
    },  # type: ignore[dict-item]
)
def get_ground_station(
    gs_id: int,
    db: Session = Depends(get_db),
    current_user: UserModel = Depends(get_current_user),
):
    # any authenticated user can read (for now)
    return GroundStationService.get_ground_station(db, gs_id)


# DELETE /api/v1/gs/{gs_id}
@router.delete(
    "/{gs_id}",
    summary="Delete a ground station",
    response_description="Deleted ground station object",
    responses={
        **getErrorResponses(403),
        **getErrorResponses(404),
        **getErrorResponses(409),
        **getErrorResponses(503),
        **getErrorResponses(500),
    },  # type: ignore[dict-item]
)
def delete_ground_station(
    gs_id: int,
    db: Session = Depends(get_db),
    current_user: UserModel = Depends(get_current_user),
):
    # 🔒 only system_admin can delete GS
    require_system_admin(current_user)
    return GroundStationService.delete_ground_station(db, gs_id)
