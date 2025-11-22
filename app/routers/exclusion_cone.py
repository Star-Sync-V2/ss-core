import uuid
from fastapi import APIRouter, Depends
from typing import List
from sqlmodel import Session

from app.models.exclusion_cone import (
    ExclusionConeModel,
    ExclusionConeCreateModel,
    ExclusionConeUpdateModel,
)
from app.services.db import get_db
from app.services.exclusion_cone import ExclusionConeService
from app.services.auth import get_current_user
from app.models.user import UserModel
from app.routers.error import getErrorResponses
from app.models.user import UserModel
from app.services.auth import get_current_user

router = APIRouter(prefix="/excones", tags=["Exclusion Cone"])

# POST create cone
@router.post(
    "/",
    summary="Create a new ExclusionCone",
    response_model=ExclusionConeModel,
    response_description="Created exclusion cone object",
    responses={**getErrorResponses(503), **getErrorResponses(500)},  # type: ignore[dict-item]
)
def create_exclusion_cone(
    request: ExclusionConeCreateModel,
    db: Session = Depends(get_db),
    current_user: UserModel = Depends(get_current_user),
):
    return ExclusionConeService.create_exclusion_cone(db, request, current_user)


# PATCH update
@router.patch(
    "/{excone_id}",
    summary="Update exclusion cone",
    response_model=ExclusionConeModel,
    response_description="Updated exclusion cone object",
    responses={**getErrorResponses(404), **getErrorResponses(503), **getErrorResponses(500)},  # type: ignore[dict-item]
)
def update_exclusion_cone(
    excone_id: uuid.UUID,
    request: ExclusionConeUpdateModel,
    db: Session = Depends(get_db),
    current_user: UserModel = Depends(get_current_user),
):
    return ExclusionConeService.update_exclusion_cone(db, excone_id, request, current_user)


# GET list cones
@router.get(
    "/",
    summary="Get a list of all exclusion_cones",
    response_model=List[ExclusionConeModel],
    response_description="List of exclusion cone objects",
    responses={**getErrorResponses(503), **getErrorResponses(500)},  # type: ignore[dict-item]
)
def get_exclusion_cones(
    db: Session = Depends(get_db),
    current_user: UserModel = Depends(get_current_user),
):
    return ExclusionConeService.get_exclusion_cones(db, current_user)


@router.get(
    "/{excone_id}",
    summary="Get a exclusion_cone by id",
    response_model=ExclusionConeModel,
    response_description="Specific exclusion object",
    responses={**getErrorResponses(404), **getErrorResponses(503), **getErrorResponses(500)},  # type: ignore[dict-item]
)
def get_exclusion_cone(
    excone_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: UserModel = Depends(get_current_user),
):
    return ExclusionConeService.get_exclusion_cone(db, excone_id, current_user)


@router.delete(
    "/{excone_id}",
    summary="Delete a exclusion_cone",
    response_model=ExclusionConeModel,
    response_description="Deleted exclusion cone object",
    responses={**getErrorResponses(404), **getErrorResponses(409), **getErrorResponses(503), **getErrorResponses(500)},  # type: ignore[dict-item]
)
def delete_exclusion_cone(
    excone_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: UserModel = Depends(get_current_user),
):
    return ExclusionConeService.delete_exclusion_cone(db, excone_id, current_user)
