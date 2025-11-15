from datetime import datetime
from typing import Optional
from sqlmodel import SQLModel, Field  # type: ignore

class User(SQLModel, table=True):
    """User model for authentication"""

    __tablename__: str = "users"  # type: ignore

    id: Optional[int] = Field(default=None, primary_key=True)
    username: str = Field(unique=True, index=True)
    email: str = Field(unique=True, index=True)
    hashed_password: str
    is_active: bool = Field(default=True)
    created_at: datetime = Field(default_factory=datetime.now)
    first_name: Optional[str] = Field(nullable=False, default="")
    last_name: Optional[str] = Field(nullable=False, default="")

    # keep default "user" so existing rows still make sense
    role: str = Field(
        nullable=False,
        default="user",
        description=(
            "Role of the user "
            "(admin/user legacy, or system_admin/system_user/mission_admin/mission_user)"
        ),
    )

    # 🔹 NEW: mission scoping (nullable)
    mission_id: Optional[int] = Field(
        default=None,
        description="Mission this user is associated with (for mission_* roles)",
        nullable=True,
    )


class UserCreate(SQLModel):
    """Schema for user creation"""

    username: str
    email: str
    password: str

    # Optional; default stays 'user' for backwards compatibility
    role: str = "user"
    mission_id: Optional[int] = None


class UserRead(SQLModel):
    """Schema for user response"""

    id: int
    username: str
    email: str
    is_active: bool
    role: str
    mission_id: Optional[int] = None
