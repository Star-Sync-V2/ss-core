# app/models/mission.py
from typing import Optional
from pydantic import BaseModel, Field


class MissionBaseModel(BaseModel):
    name: str = Field(description="Unique mission name", examples=["SCISAT"])
    description: Optional[str] = Field(
        default=None,
        description="Optional mission description",
        examples=["Canadian SCISAT mission"],
    )


class MissionCreateModel(MissionBaseModel):
    pass


class MissionReadModel(MissionBaseModel):
    id: int = Field(description="Mission ID", examples=[1])


class MissionUpdateModel(BaseModel):
    name: Optional[str] = Field(
        default=None, description="Unique mission name", examples=["SCISAT-NEW"]
    )
    description: Optional[str] = Field(
        default=None,
        description="Optional mission description",
        examples=["Updated description"],
    )
