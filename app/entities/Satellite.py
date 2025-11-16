import uuid
from skyfield.sgp4lib import EarthSatellite  # type: ignore
from sqlmodel import Relationship, SQLModel, Field  # type: ignore
from sqlalchemy.orm import Mapped
from typing import List
from app.entities.ExclusionCone import ExclusionCone
from typing import List, Optional


class Satellite(SQLModel, table=True):
    __tablename__: str = "satellites"  # type: ignore

    id: uuid.UUID = Field(primary_key=True)
    name: str
    tle: str
    uplink: float
    telemetry: float
    science: float
    priority: int
    ex_cones: Mapped[List["ExclusionCone"]] = Relationship(back_populates="satellite")
    
    mission_id: Optional[int] = Field(
        default=None,
        nullable=True,
        description="Mission this satellite belongs to",
    )
    # this init will most likely be removed soon
    def __init__(
        self,
        id: uuid.UUID | None = None,
        name: str = "",
        tle: str = "",
        uplink: float = 0,
        telemetry: float = 0,
        science: float = 0,
        priority: int = 0,
        mission_id: Optional[int] = None,  
        # ex_cone: Optional[List[ExclusionCone]] = None,
    ):
        self.id = id if id is not None else uuid.uuid4()
        self.name = name
        self.tle = tle
        self.uplink = uplink
        self.telemetry = telemetry
        self.science = science
        # self.ex_cone = ex_cone
        self.priority = priority
        self.mission_id = mission_id       # 👈 new

    def get_sf_sat(self) -> EarthSatellite:
        tle_lines = self.tle.splitlines()
        satellite = EarthSatellite(tle_lines[1], tle_lines[2], tle_lines[0])
        return satellite

    def __repr__(self):
        return f"Satellite(name={self.name})"
