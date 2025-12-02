# app/routers/hello.py

from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session, select
import logging

from app.services.db import get_db, create_db_and_tables
from app.entities.Mission import Mission
from app.entities.Satellite import Satellite
from app.entities.GroundStation import GroundStation
from app.entities.Request import RFRequest

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/hello",
    tags=["hello"],
)


@router.get("/")
def hello():
    return {"message": "Hello, World!"}


@router.get(
    "/initdb",
    summary="Initialize the database",
    response_description="Database and tables created",
)
def initdb():
    create_db_and_tables()
    return {"message": "Database and tables created"}


@router.post(
    "/create_demo_data",
    summary="Create demo mission/satellite/GS/requests",
    response_description="Demo data created",
)
def create_demo_data(db: Session = Depends(get_db)):
    """
    Create a minimal, scheduler-ready dataset:

    - One Mission ("DemoMission")
    - One Satellite attached to that mission
    - One Ground Station
    - One RFRequest in the window 2025-12-02 00:00–06:00

    Idempotent-ish: reuses existing Mission/Sat/GS with the same names
    instead of crashing on unique constraints.
    """

    try:
        # -------------------------
        # 1) Mission
        # -------------------------
        mission_name = "DemoMission"
        mission = db.exec(
            select(Mission).where(Mission.name == mission_name)
        ).first()

        if mission is None:
            mission = Mission(
                name=mission_name,
                description="Demo mission for scheduler smoke tests",
            )
            db.add(mission)
            db.commit()
            db.refresh(mission)

        # -------------------------
        # 2) Satellite
        # -------------------------
        sat_name = "DEMO-SAT-1"
        satellite = db.exec(
            select(Satellite).where(Satellite.name == sat_name)
        ).first()

        if satellite is None:
            tle = (
                "DEMO-SAT-1\n"
                "1 25544U 98067A   24298.42572809  .00002329  00000+0  31378-3 0  9994\n"
                "2 25544  51.6449  21.2211 0007413  37.8061  75.9350 15.48815356313634"
            )

            satellite = Satellite(
                name=sat_name,
                tle=tle,
                uplink=40.0,
                telemetry=100.0,
                science=100.0,
                priority=1,
                mission_id=mission.id,
            )
            db.add(satellite)
            db.commit()
            db.refresh(satellite)

        # -------------------------
        # 3) Ground Station
        # -------------------------
        gs_name = "DEMO-GS-1"
        ground_station = db.exec(
            select(GroundStation).where(GroundStation.name == gs_name)
        ).first()

        if ground_station is None:
            ground_station = GroundStation(
                name=gs_name,
                lat=45.0,
                lon=-75.0,
                height=100.0,
                mask=5,
                uplink=40.0,
                downlink=100.0,
                science=100.0,
            )
            db.add(ground_station)
            db.commit()
            db.refresh(ground_station)

        # -------------------------
        # 4) RF Request in known window
        # -------------------------
        # NOTE: keep these *naive* (no tzinfo) to match how your DB stores datetimes
        window_start = datetime(2025, 12, 2, 0, 0, 0)
        window_end = datetime(2025, 12, 2, 6, 0, 0)

        existing_rf = db.exec(
            select(RFRequest).where(
                RFRequest.satellite_id == satellite.id,
                RFRequest.mission_id == mission.id,
                RFRequest.start_time == window_start,
                RFRequest.end_time == window_end,
            )
        ).first()

        if existing_rf is None:
            min_passes = 1

            rf_request = RFRequest(
                mission=mission.name,
                satellite_id=satellite.id,
                start_time=window_start,
                end_time=window_end,
                contact_id=None,
                scheduled=False,
                priority=1,
                uplink_time_requested=600,
                downlink_time_requested=600,
                science_time_requested=300,
                min_passes=min_passes,
                ground_station_id=None,  # scheduler can choose GS
                time_remaining=600,       # or max of the requested times
                num_passes_remaining=min_passes,  # 👈 IMPORTANT: real int, not FieldInfo
                mission_id=mission.id,
            )
            db.add(rf_request)
            db.commit()
            db.refresh(rf_request)

        else:
            rf_request = existing_rf

        return {
            "message": "Demo data created",
            "missionId": mission.id,
            "satelliteId": str(satellite.id),
            "groundStationId": ground_station.id,
            "rfRequestId": str(rf_request.id),
        }

    except Exception as e:
        # This makes Swagger show the real error instead of plain "Internal Server Error"
        logger.exception("Error while creating demo data")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error while creating demo data: {e}",
        )
