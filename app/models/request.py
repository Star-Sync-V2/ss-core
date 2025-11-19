import asyncio
from datetime import datetime, timedelta
from typing import List, Optional
from pydantic import BaseModel, Field
from uuid import UUID


class RFTimeRequestModel(BaseModel):
    missionName: str = Field(
        description="Name of the mission making the request", examples=["SCISAT"]
    )
    # will have to rename the field to satelliteName and supply the actual name of the satellite
    satelliteId: UUID = Field(
        description="Name of the satellite the request is for",
        examples=["228f21de-116c-493a-9982-8ee24d9f57bf"],
    )
    # the example times would probably have to be modified eventually
    # this is just to prevent confusion when trying out api endpoints through swagger
    startTime: datetime = Field(
        description="The beginning of the time window during which the requested time should be provided in",
        examples=[datetime.now() + timedelta(minutes=30)],
    )
    endTime: datetime = Field(
        description="The end of the time window during which the requested time should be provided in",
        examples=[datetime.now() + timedelta(days=1, minutes=30)],
    )
    uplinkTime: int = Field(
        description="Time in seconds that the mission is requesting uplink support",
        examples=[600],
    )
    downlinkTime: int = Field(
        description="Time in seconds that the mission is requesting support for downlinking spacecraft telemetry",
        examples=[600],
    )
    scienceTime: int = Field(
        description="Time in seconds that the mission is requesting support for downlinking science data",
        examples=[150],
    )
    minimumNumberOfPasses: Optional[int] = Field(
        default=1,
        description="The minimum number of passes that should be provided to the mission in support of this request",
        examples=[2],
    )
    mission_id: Optional[int] = Field(
        default=None,
        description="Mission this request belongs to"
    )



class ContactRequestModel(BaseModel):
    missionName: str = Field(
        description="Name of the mission making the request", examples=["SCISAT"]
    )
    # will have to rename the field to satelliteName and supply the actual name of the satellite
    satelliteId: UUID = Field(
        description="Name of the satellite the request is for",
        examples=["228f21de-116c-493a-9982-8ee24d9f57bf"],
    )
    station_id: int = Field(description="The station the request is for", examples=[1])
    orbit: int = Field(
        description="The orbit number of the satellite at the time of AOS",
        examples=[1234],
    )
    uplink: bool = Field(
        description="Is an uplink required for this contact", examples=[True]
    )
    telemetry: bool = Field(
        description="Is telemetry downlink required for this contact", examples=[True]
    )
    science: bool = Field(
        description="Is science downlink required for this contact", examples=[False]
    )
    # the example times would probably have to be modified eventually
    aosTime: datetime = Field(
        description="Time of the Acquisition of Signal for the contact",
        examples=[datetime.now() + timedelta(minutes=30)],
    )
    rfOnTime: datetime = Field(
        description="Time at which the elevation angle satisfies station mask for a given ground station",
        examples=[datetime.now() + timedelta(minutes=32)],
    )
    rfOffTime: datetime = Field(
        description="Time at which the elevation angle satisfies station mask for a given ground station",
        examples=[datetime.now() + timedelta(minutes=48)],
    )
    losTime: datetime = Field(
        description="Time of the Loss of Signal for the contact",
        examples=[datetime.now() + timedelta(minutes=50)],
    )
    mission_id: Optional[int] = Field(
        default=None,
        description="Mission this request belongs to"
    )


class GeneralContactResponseModel(BaseModel):
    """
    This is a general response model for both RF time and contact requests.
    """
    id: UUID = Field(
        description="The ID of the request",
        examples=["228f21de-116c-493a-9982-8ee24d9f57bf"],
    )
    requestType: str = Field(
        description="Type of the request (either RF or Contact)", examples=["RFTime"]
    )
    mission: str = Field(
        description="Name of the mission making the request", examples=["SCISAT"]
    )
    satellite_name: str = Field(
        description="Name of the satellite the request is for", examples=["SCISAT-1"]
    )
    station_id: int = Field(description="The station the request is for", examples=[1])
    orbit: Optional[int] = Field(
        description="The orbit number of the satellite at the time of AOS",
        examples=[1234],
    )
    uplink: int = Field(
        description="Is an uplink required for this contact", examples=[True]
    )
    telemetry: int = Field(
        description="Is telemetry downlink required for this contact", examples=[True]
    )
    science: int = Field(
        description="Is science downlink required for this contact", examples=[False]
    )
    startTime: datetime = Field(
        description="The beginning of the time window during which the requested time will be provided in",
        examples=["2024-10-15T12:00:00"],
    )
    endTime: datetime = Field(
        description="The end of the time window during which the requested time will be provided in",
        examples=["2024-10-15T12:20:00"],
    )
    duration: float = Field(
        description="Duration of the request in seconds", examples=[1200]
    )
    aos: Optional[datetime] = Field(
        description="Time of the Acquisition of Signal for the contact",
        examples=["2024-10-15T12:00:00"],
    )
    rf_on: Optional[datetime] = Field(
        description="Time at which the elevation angle satisfies station mask for a given ground station",
        examples=["2024-10-15T12:05:00"],
    )
    rf_off: Optional[datetime] = Field(
        description="Time at which the elevation angle satisfies station mask for a given ground station",
        examples=["2024-10-15T12:15:00"],
    )
    los: Optional[datetime] = Field(
        description="Time of the Loss of Signal for the contact",
        examples=["2024-10-15T12:20:00"],
    )
   # 🔹 ADD THIS
    mission_id: Optional[int] = Field(
        default=None,
        description="Mission this request belongs to",
        examples=[1],
    )

    class Config:
        # Pydantic's default datetime format to serialize `datetime` to ISO 8601 string
        json_encoders = {datetime: lambda v: v.isoformat() if v is not None else None}
