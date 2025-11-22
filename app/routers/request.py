from typing import List
from fastapi import APIRouter, HTTPException, Depends
from app.services.db import get_db
from sqlmodel import Session
from uuid import UUID
from app.models.request import (
    GeneralContactResponseModel,
    RFTimeRequestModel,
    ContactRequestModel,
)
from app.entities.Request import (
    ContactRequest,
    RFRequest,
)
from app.services.request import RequestService, Booking
import logging
from app.routers.error import getErrorResponses
from app.models.user import UserModel
from app.services.auth import get_current_user
from app.services.permissions import (
    SYSTEM_ADMIN,
    SYSTEM_USER,
    MISSION_ADMIN,
    MISSION_USER,
)
from app.models.user import UserModel
from app.services.auth import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/request",
    tags=["Request"],
    responses={404: {"description": "Not found"}},
)


@router.get(
    "/",
    summary="Get all requests",
    response_model=List[GeneralContactResponseModel],
    responses={**getErrorResponses(503), **getErrorResponses(500)},  # type: ignore[dict-item]
)
def get_requests(
    db: Session = Depends(get_db),
    current_user: UserModel = Depends(get_current_user),
):
    try:
        return RequestService.get_all_transformed_requests(db, current_user)

    except Exception as e:
        logger.error(f"Error getting all requests: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/bookings",
    summary="Get all bookings",
    response_model=List[Booking],
    responses={**getErrorResponses(503), **getErrorResponses(500)},  # type: ignore[dict-item]
)
def get_bookings(
    db: Session = Depends(get_db),
    current_user: UserModel = Depends(get_current_user),

):
    try:
        return RequestService.get_bookings(db, current_user)
    except Exception as e:
        logger.error(f"Error getting bookings: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/sample",
    summary="runs a sample demo of the service",
    response_model=List[GeneralContactResponseModel],
    responses={**getErrorResponses(400), **getErrorResponses(503), **getErrorResponses(500)},  # type: ignore[dict-item]
)
def sample(
    request: ContactRequestModel,
    db: Session = Depends(get_db),
    current_user: UserModel = Depends(get_current_user),
):
    try:
        future_reqs = RequestService.sample(db, request, current_user)
        return future_reqs
    except HTTPException as e:
        raise e
    except Exception as e:
        logger.error(f"Error in sample: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post(
    "/rf-time",
    summary="Ground Station RF Time Request",
    response_model=RFRequest,
    response_description="Request body",
    responses={**getErrorResponses(400), **getErrorResponses(503), **getErrorResponses(500)},  # type: ignore[dict-item]
)
def rf_time(
    request: RFTimeRequestModel,
    db: Session = Depends(get_db),
    current_user: UserModel = Depends(get_current_user),
):
    try:
        created_request = RequestService.create_rf_request(db, request, current_user)
        return created_request

    except HTTPException as e:
        raise e
    except Exception as e:
        logger.error(f"Error creating RF request: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post(
    "/contact",
    summary="Ground Station Contact Request",
    response_model=ContactRequest,
    response_description="Simple success string for now",
    responses={**getErrorResponses(400), **getErrorResponses(503), **getErrorResponses(500)},  # type: ignore[dict-item]
)
def contact(request: ContactRequestModel, db: Session = Depends(get_db), current_user: UserModel = Depends(get_current_user)):
    try:
        resp = RequestService.create_contact_request(db, request, current_user)
        return resp
    except HTTPException as e:
        raise e
    except Exception as e:
        logger.error(f"Error creating contact request: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/rf-time/{request_id}",
    summary="Get RF Time Request by ID",
    response_model=RFRequest,
    responses={**getErrorResponses(404), **getErrorResponses(503), **getErrorResponses(500)},  # type: ignore[dict-item]
)
def get_rf_time_request(request_id: UUID, db: Session = Depends(get_db)):
    try:
        request = RequestService.get_rf_time_request(db, request_id)
        return request
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting RF time request: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete(
    "/rf-time/{request_id}",
    summary="Delete RF Time Request by ID",
    responses={**getErrorResponses(404), **getErrorResponses(503), **getErrorResponses(500)},  # type: ignore[dict-item]
)
def delete_rf_time_request(request_id: UUID, db: Session = Depends(get_db)):
    try:
        RequestService.delete_rf_time_request(db, request_id)
        return {"message": "RF Time Request deleted successfully"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting RF time request: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/contact/{request_id}",
    summary="Get Contact Request by ID",
    response_model=ContactRequestModel,
    responses={**getErrorResponses(404), **getErrorResponses(503), **getErrorResponses(500)},  # type: ignore[dict-item]
)
def get_contact_request(request_id: UUID, db: Session = Depends(get_db)):
    try:
        return RequestService.get_contact_request(db, request_id)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting contact request: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete(
    "/contact/{request_id}",
    summary="Delete Contact Request by ID", 
    responses={**getErrorResponses(404), **getErrorResponses(503), **getErrorResponses(500)},  # type: ignore[dict-item]
)
def delete_contact_request(request_id: UUID, db: Session = Depends(get_db)):
    try:
        RequestService.delete_contact_request(db, request_id)
        return {"message": "Contact Request deleted successfully"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting contact request: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
