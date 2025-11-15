from typing import Optional
from datetime import datetime
from pydantic import BaseModel, Field, field_validator


# Allowed roles (include old ones so existing data still works)
ALLOWED_ROLES = {
    "admin",          # legacy
    "user",           # legacy
    "system_admin",
    "system_user",
    "mission_admin",
    "mission_user",
}


class UserBaseModel(BaseModel):
    username: str = Field(description="Username", examples=["johndoe"])
    email: str = Field(description="User email", examples=["johndoe@email.com"])
    is_active: bool = Field(description="Is user active", examples=[True])
    first_name: Optional[str] = Field(
        description="User's first name", examples=["John"]
    )
    last_name: Optional[str] = Field(
        description="User's last name", examples=["Doe"]
    )
    role: str = Field(
        description=(
            "User's role "
            "(admin/user legacy, or system_admin/system_user/mission_admin/mission_user)"
        ),
        examples=["system_admin"],
    )
    # 🔹 NEW: mission scoping; used for mission_* roles
    mission_id: Optional[int] = Field(
        default=None,
        description="Mission this user is associated with (for mission_* roles)",
        examples=[1],
    )


class UserModel(UserBaseModel):
    """
    Pydantic model to represent a user.
    """

    id: int = Field(description="User ID", examples=[1])
    created_at: Optional[datetime] = Field(
        description="Date user was created", examples=[datetime.now()]
    )

    class Config:
        from_attributes = True


class UserUpdateModel(BaseModel):
    """
    Pydantic model for updating user details.
    """

    username: Optional[str] = Field(
        default=None, description="Username", examples=["johndoe"]
    )
    password: Optional[str] = Field(
        default=None, description="Password", examples=["password"]
    )
    email: Optional[str] = Field(
        default=None, description="User email", examples=["johndoe@gmail.com"]
    )
    is_active: Optional[bool] = Field(
        default=None, description="Is user active", examples=[True]
    )
    first_name: Optional[str] = Field(
        default=None, description="User's first name", examples=["John"]
    )
    last_name: Optional[str] = Field(
        default=None, description="User's last name", examples=["Doe"]
    )
    role: Optional[str] = Field(
        default=None,
        description=(
            "User's role "
            "(admin/user legacy, or system_admin/system_user/mission_admin/mission_user)"
        ),
        examples=["system_user"],
    )
    # 🔹 NEW: allow updating mission
    mission_id: Optional[int] = Field(
        default=None,
        description="Mission this user is associated with (for mission_* roles)",
        examples=[1],
    )

    @field_validator("role")
    def validate_role(cls, value):
        if value is None:
            return value
        if value not in ALLOWED_ROLES:
            raise ValueError(
                "Role must be one of: "
                + ", ".join(sorted(ALLOWED_ROLES))
            )
        return value

    class Config:
        from_attributes = True
