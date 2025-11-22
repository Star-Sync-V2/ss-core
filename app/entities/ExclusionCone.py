# app/entities/ExclusionCone.py
import uuid
from uuid import UUID
from typing import TYPE_CHECKING, Optional

from sqlmodel import SQLModel, Field, Relationship  # type: ignore

if TYPE_CHECKING:
    from app.entities.Satellite import Satellite


class ExclusionCone(SQLModel, table=True):
    __tablename__ = "exclusion_cones"  # must match DB table name

    id: UUID = Field(default_factory=uuid.uuid4, primary_key=True)

    # free-text mission name (kept from old schema)
    mission: str

    # 👇 mission_id is an INT FK → mission.id (because Mission.id is int)
    mission_id: Optional[int] = Field(
        default=None,
        foreign_key="mission.id",  # matches Mission.__tablename__ = "mission"
    )

    angle_limit: float
    interfering_satellite: str

    satellite_id: UUID = Field(foreign_key="satellites.id")
    gs_id: int = Field(foreign_key="ground_stations.id")

    satellite: "Satellite" = Relationship(back_populates="ex_cones")
