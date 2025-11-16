from typing import List, Optional
import uuid
from pydantic import BaseModel, Field
from app.models.exclusion_cone import ExclusionConeModel


class SatelliteCreateModel(BaseModel):
    """
    A pydantic model class representing the satellite. Only used for creation of new resources.
    """

    name: str = Field(
        description="Name of the satellite",
        examples=["SCISAT 1"],
    )
    tle: str = Field(
        description="TLE of the satellite",
        examples=[
            "SCISAT 1\n1 27858U 03036A   24298.42572809  .00002329  00000+0  31378-3 0  9994\n2 27858  73.9300 283.7690 0006053 131.3701 228.7996 14.79804256142522"
        ],
    )
    uplink: float = Field(ge=0, description="Uplink data rate in Kbps", examples=[40.0])
    telemetry: float = Field(
        ge=0, description="Downlink data rate in Mbps", examples=[100.0]
    )
    science: float = Field(
        ge=0, description="Science data rate in Mbps", examples=[100.0]
    )
    priority: int = Field(ge=0, description="Priority of the satellite", examples=[1])
    
     # 🔹 NEW
    mission_id: Optional[int] = Field(
        default=None,
        description="Mission this satellite belongs to",
        examples=[1],
    )

class SatelliteModel(SatelliteCreateModel):
    """
    A pydantic model class representing the satellite.
    """

    id: uuid.UUID = Field(
        description="ID of the satellite",
        examples=["7b16adda-0dfc-48d0-9902-0da6da504a71"],
    )
    ex_cones: List["ExclusionConeModel"] = Field(
        default_factory=list,
        description="List of exclusion cones",
        examples=[[]],
    )

    class Config:
        from_attributes = True  # Allow conversion from SQLModel object


class SatelliteUpdateModel(BaseModel):
    """
    A pydantic model class representing the satellite. Only used for updating satellites, hence all fields are optional.
    """

    name: Optional[str] = Field(
        default=None,
        description="Name of the satellite",
        examples=["SCISAT 1"],
    )
    tle: Optional[str] = Field(
        default=None,
        description="TLE of the satellite",
        examples=[
            "SCISAT 1\n1 27858U 03036A   24298.42572809  .00002329  00000+0  31378-3 0  9994\n2 27858  73.9300 283.7690 0006053 131.3701 228.7996 14.79804256142522"
        ],
    )
    uplink: Optional[float] = Field(
        ge=0, default=None, description="Uplink data rate in Kbps", examples=[40.0]
    )
    telemetry: Optional[float] = Field(
        ge=0, default=None, description="Downlink data rate in Mbps", examples=[100.0]
    )
    science: Optional[float] = Field(
        ge=0, default=None, description="Science data rate in Mbps", examples=[100.0]
    )
    priority: Optional[int] = Field(
        ge=0, default=None, description="Priority of the satellite", examples=[1]
    )
    # 🔹 NEW
    mission_id: Optional[int] = Field(
        default=None,
        description="Mission this satellite belongs to",
        examples=[1],
    )
