from typing import List
from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from ..models.gs import MockRequest
from ..services.gs import generate_mock_data
from app.services.auth import get_current_user
from app.models.user import UserModel
from app.services.permissions import require_system_admin

router = APIRouter(
    prefix="/gs",
    tags=["gs"],
    responses={404: {"description": "Not found"}},
)


@router.post(
    "/mock",
    summary="Generate mock data for ground stations",
    response_model=List[bool],
    response_description=(
        "List of boolean values that are equal to the ground stations "
        "availability at each time interval"
    ),
)
async def gs_mock(
    request: MockRequest,
    current_user: UserModel = Depends(get_current_user),
):
    # 🔒 Only system_admin can generate mock GS data
    require_system_admin(current_user)

    # You could just `return generate_mock_data(request)` and let FastAPI handle JSON,
    # but keeping your JSONResponse is fine too:
    return JSONResponse(content=generate_mock_data(request))
