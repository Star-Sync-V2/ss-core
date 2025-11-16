# app/entities/Mission.py
from sqlmodel import SQLModel, Field


class Mission(SQLModel, table=True):
    __tablename__ = "mission"

    id: int | None = Field(default=None, primary_key=True)
    name: str = Field(index=True, unique=True)
    description: str | None = None
