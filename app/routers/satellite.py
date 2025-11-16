import uuid
from fastapi import APIRouter, Depends
from typing import List
from sqlmodel import Session

from app.models.satellite import (
    SatelliteModel,
    SatelliteCreateModel,
    SatelliteUpdateModel,
)
from app.routers.error import getErrorResponses
from app.services.db import get_db
from app.services.satellite import SatelliteService

from app.services.auth import get_current_user
from app.models.user import UserModel
from app.services.permissions import require_write_access

router = APIRouter(prefix="/satellites", tags=["Satellite"])


# POST /api/v1/satellites
@router.post(
    "/",
    summary="Create a new Satellite",
    response_model=SatelliteModel,
    response_description="Created satellite object",
    responses={
        **getErrorResponses(403),
        **getErrorResponses(503),
        **getErrorResponses(500),
    },  # type: ignore[dict-item]
)
def create_satellite(
    request: SatelliteCreateModel,
    db: Session = Depends(get_db),
    current_user: UserModel = Depends(get_current_user),
):
    # 🔒 system_admin + mission_admin can write
    require_write_access(current_user)
    return SatelliteService.create_satellite(db, request, current_user)


# PATCH /api/v1/satellites/{satellite_id}
@router.patch(
    "/{satellite_id}",
    summary="Update a Satellite",
    response_model=SatelliteModel,
    response_description="Updated satellite object",
    responses={
        **getErrorResponses(403),
        **getErrorResponses(404),
        **getErrorResponses(503),
        **getErrorResponses(500),
    },  # type: ignore[dict-item]
)
def update_satellite(
    satellite_id: uuid.UUID,
    request: SatelliteUpdateModel,
    db: Session = Depends(get_db),
    current_user: UserModel = Depends(get_current_user),
):
    require_write_access(current_user)
    return SatelliteService.update_satellite(db, satellite_id, request, current_user)


# GET /api/v1/satellites
@router.get(
    "/",
    summary="Get a list of all satellites",
    response_model=List[SatelliteModel],
    response_description="List of satellite objects",
    responses={**getErrorResponses(503), **getErrorResponses(500)},  # type: ignore[dict-item]
)
def get_satellites(
    db: Session = Depends(get_db),
    current_user: UserModel = Depends(get_current_user),
):
    # any authenticated user can read
    return SatelliteService.get_satellites(db, current_user)


# GET /api/v1/satellites/{satellite_id}
@router.get(
    "/{satellite_id}",
    summary="Get a satellite by id",
    response_model=SatelliteModel,
    response_description="Specific satellite object",
    responses={
        **getErrorResponses(404),
        **getErrorResponses(503),
        **getErrorResponses(500),
    },  # type: ignore[dict-item]
)
def get_satellite(
    satellite_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: UserModel = Depends(get_current_user),
):
    # any authenticated user can read
    return SatelliteService.get_satellite(db, satellite_id, current_user)


# DELETE /api/v1/satellites/{satellite_id}
@router.delete(
    "/{satellite_id}",
    summary="Delete a Satellite",
    response_model=SatelliteModel,
    response_description="Deleted satellite object",
    responses={
        **getErrorResponses(403),
        **getErrorResponses(404),
        **getErrorResponses(409),
        **getErrorResponses(503),
        **getErrorResponses(500),
    },  # type: ignore[dict-item]
)
def delete_satellite(
    satellite_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: UserModel = Depends(get_current_user),
):
    require_write_access(current_user)
    return SatelliteService.delete_satellite(db, satellite_id, current_user)
