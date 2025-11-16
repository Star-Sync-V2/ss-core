from fastapi import HTTPException
from app.models.user import UserModel  # or use entities.User if you prefer


SYSTEM_ADMIN = "system_admin"
SYSTEM_USER = "system_user"
MISSION_ADMIN = "mission_admin"
MISSION_USER = "mission_user"


def require_system_admin(current_user: UserModel) -> None:
    if current_user.role != SYSTEM_ADMIN:
        raise HTTPException(status_code=403, detail="Permission denied")


def is_system_role(current_user: UserModel) -> bool:
    return current_user.role in (SYSTEM_ADMIN, SYSTEM_USER)


def is_mission_role(current_user: UserModel) -> bool:
    return current_user.role in (MISSION_ADMIN, MISSION_USER)


def require_write_access(current_user: UserModel) -> None:
    """
    Very simple first pass:
    - system_admin and mission_admin can write
    - others are read-only
    """
    if current_user.role not in (SYSTEM_ADMIN, MISSION_ADMIN):
        raise HTTPException(status_code=403, detail="Write access denied")