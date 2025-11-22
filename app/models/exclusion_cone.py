from typing import Optional
import uuid
from pydantic import BaseModel, Field


class ExclusionConeCreateModel(BaseModel):
    """
    This is a Pydantic model class that represents the exclusion cone;
    Only used for creation of new resources.
    """

    mission: str = Field(
        description="Name of the mission",
        examples=["SCISAT"],
    )
    angle_limit: float = Field(
        ge=0, description="The limiting angle between the two objects.", examples=[5.0]
    )
    interfering_satellite: str = Field(
        description="The satellite which must be deconflicted against.",
        examples=["OTHER SAT"],
    )
    satellite_id: uuid.UUID = Field(
        description="The satellite ID the request is for",
        examples=["7b16adda-0dfc-48d0-9902-0da6da504a71"],
    )
    gs_id: int = Field(
        ge=0,
        description="The station for which the exclusion cone will apply.",
        examples=[1],
    )


class ExclusionConeModel(ExclusionConeCreateModel):
    """
    This is a Pydantic model class that represents the exclusion cone.
    """

    id: uuid.UUID = Field(
        description="ID of the exclusion cone",
        examples=["4ff2dab7-bffe-414d-88a5-1826b9fea8df"],
    )

    class Config:
        from_attributes = True  # Allow conversion from SQLModel objects


class ExclusionConeUpdateModel(BaseModel):
    """
    This is a Pydantic model only used for updating exclusion cones.
    """

    mission: Optional[str] = Field(
        default=None,
        description="Name of the mission",
        examples=["SCISAT"],
    )
    angle_limit: Optional[float] = Field(
        ge=0,
        default=None,
        description="The limiting angle between the two objects.",
        examples=[5.0],
    )
    interfering_satellite: Optional[str] = Field(
        default=None,
        description="The satellite which must be deconflicted against.",
        examples=["OTHER SAT"],
    )
    satellite_id: Optional[uuid.UUID] = Field(
        default=None,
        description="The satellite ID the request is for",
        examples=["7b16adda-0dfc-48d0-9902-0da6da504a71"],
    )
    gs_id: Optional[int] = Field(
        ge=0,
        default=None,
        description="The station for which the exclusion cone will apply.",
        examples=[1],
    )
    mission_id: Optional[int] = None


    class Config:
        from_attributes = True  # Allow conversion from SQLModel objects
