from collections import defaultdict
from dataclasses import dataclass
import datetime
from pprint import pprint
import random
import numpy as np
from skyfield.api import EarthSatellite, load, Timescale, Time
from skyfield.toposlib import GeographicPosition
from sqlmodel import select, Session
from app.models.request import GeneralContactResponseModel
from app.services.ground_station import GroundStationService
from app.services.satellite import SatelliteService
from app.entities.Satellite import Satellite
from app.entities.GroundStation import GroundStation
from app.entities.Request import RFRequest, ContactRequest
from app.models.request import ContactRequestModel, RFTimeRequestModel
import uuid
import logging
from uuid import UUID
from sqlalchemy.exc import SQLAlchemyError
from fastapi import HTTPException
from app.models.user import UserModel
from app.services.permissions import is_system_role, is_mission_role
from app.services.permissions import (
    SYSTEM_ADMIN,
    SYSTEM_USER,
    MISSION_ADMIN,
    MISSION_USER,
)
from app.services.auth import get_current_user
logger = logging.getLogger(__name__)

random.seed(42)


@dataclass
class Slot:
    start_time: datetime.datetime
    end_time: datetime.datetime


@dataclass
class Booking:
    slot: Slot
    gs_id: int
    request_id: uuid.UUID
    id: uuid.UUID


Request = RFRequest | ContactRequest
# we have to take in a list of requests and generate a list of contacts
# the goal is to maximize the number of contacts we can make
# we can only make a contact if it is within the time window of the request


def divide_into_slots(
    start_time: datetime.datetime,
    end_time: datetime.datetime,
    slot_duration: int = 15 * 60,
):
    """Divide the time between start_time and end_time into slots of slot_duration

    Args:
        start_time (datetime.datetime): Start time of the time window
        end_time (datetime.datetime): End time of the time window
        slot_duration (int, optional): The length of each slot in seconds. Defaults to 15*60. 15 minutes.

    Returns:
        list[tuple[datetime.datetime, datetime.datetime]]: List of tuples representing the start and end time
    """
    slots: list[tuple[datetime.datetime, datetime.datetime]] = []
    current_time = start_time
    while current_time < end_time:
        slots.append(
            (current_time, current_time + datetime.timedelta(seconds=slot_duration))
        )
        current_time += datetime.timedelta(seconds=slot_duration)

    return slots


def schedule_with_slots(
    requests: list[Request], stations: list[GroundStation]
) -> list[Booking]:
    """Schedule the requests with the given slots

    Args:
        requests (list[Request]): List of requests to schedule
        stations (list[GroundStation]): List of GroundStations to schedule the requests with

    Returns:
        list[Booking]: List of bookings that were scheduled
    """
    slots: dict[str, dict[tuple[datetime.datetime, datetime.datetime], Booking]] = (
        defaultdict(dict)
    )
    bookings: list[Booking] = []
    
    # sort the requests by earliest end time
    requests.sort(key=lambda r: r.end_time)
    
    # set all requests to not scheduled
    for request in requests:
        request.scheduled = False
        
    # Schedule ContactRequests first
    for request in requests:
        if isinstance(request, ContactRequest):
            remaining_time: int = request.duration
            request_slots = divide_into_slots(request.start_time, request.end_time)
            for start, end in request_slots:
                if remaining_time <= 0:
                    break

                slot_duration: datetime.timedelta = min(
                    end - start, datetime.timedelta(seconds=remaining_time)
                )
                start_time = start
                end_time = start_time + slot_duration

                station_id = str(request.ground_station_id)

                if (start, start + slot_duration) in slots[station_id]:
                    continue

                booking = Booking(
                    slot=Slot(start_time=start_time, end_time=end_time),
                    request_id=request.id,
                    gs_id=request.ground_station_id,
                    id=uuid.uuid4(),
                )

                slots[station_id][(start, start + slot_duration)] = booking
                bookings.append(booking)
                
                # converting from float to int could cause issues in the future
                remaining_time -= int(slot_duration.total_seconds())
                request.scheduled = True

            if not request.scheduled:
                print(
                    f"Could not schedule request: {request.mission} - {request.satellite_id} - {request.ground_station_id}"
                )

    # Schedule RFRequests next
    for request in requests:
        if isinstance(request, RFRequest):
            request_slots = divide_into_slots(request.start_time, request.end_time)
            remaining_time = max(
                [
                    request.downlink_time_requested,
                    request.uplink_time_requested,
                    request.science_time_requested,
                ]
            )
            for start, end in request_slots:
                if remaining_time <= 0:
                    request.scheduled = True
                    break

                slot_duration = end - start
                start_time = start
                end_time = end
                for gs in stations:
                    station_name = gs.name
                    if (start, end) not in slots[station_name]:
                        request.ground_station_id = gs.id
                        booking = Booking(
                            request_id=request.id,
                            slot=Slot(
                                start_time=start_time,
                                end_time=end_time,
                            ),
                            gs_id=gs.id,
                            id=uuid.uuid4(),
                        )

                        slots[station_name][(start, end)] = booking
                        bookings.append(booking)
                        # converting from float to int could cause issues in the future
                        remaining_time -= int((end - start).total_seconds())
                if request.scheduled:
                    break
            if not request.scheduled:
                print(
                    f"Could not schedule request: {request.mission} - {request.satellite_id}"
                )
    pprint(requests)
    return bookings


def angle_diff(
    start_t: datetime.datetime,
    end_t: datetime.datetime,
    sat1: EarthSatellite,
    sat2: EarthSatellite,
    gs: GeographicPosition,
) -> list[tuple[datetime.datetime, float]]:
    """Calculate the angle difference between two satellites in a given time window

    Args:
        start_t (datetime.datetime): Start time of the time window
        end_t (datetime.datetime): End time of the time window
        sat1 (EarthSatellite): First satellite
        sat2 (EarthSatellite): Second satellite
        gs (GeographicPosition): Geographic position of the ground GroundStation

    Returns:
        list[tuple[datetime.datetime, float]]: List of tuples containing the time and angle difference between the two satellites
    """

    total_mins = int((end_t - start_t).total_seconds() / 60)

    ts = load.timescale()
    times = ts.utc(
        start_t.year,
        start_t.month,
        start_t.day,
        start_t.hour,
        start_t.minute + np.arange(total_mins),  # type: ignore
    )

    angles = []
    for t in times:
        sat1_observed = (sat1 - gs).at(t)
        sat2_observed = (sat2 - gs).at(t)

        # altaz command used to check visibility wrt ground GroundStation
        # third field left blank since we don't need distance
        sat1_altitude, _, _ = sat1_observed.altaz()
        sat2_altitude, _, _ = sat2_observed.altaz()

        if sat1_altitude.degrees > 0 and sat2_altitude.degrees > 0:  # type: ignore
            degree_diff = sat1_observed.separation_from(sat2_observed).degrees
            angles.append((t.utc_datetime(), degree_diff))
    return angles


def get_excl_times(
    angle_diff: list[tuple[datetime.datetime, float]], excl_angle: float
) -> list[tuple[datetime.datetime, datetime.datetime]]:
    """Get the exclusion times based on the angle difference between two satellites

    Args:
        angle_diff (list[tuple[datetime.datetime, float]]): List of tuples containing the time and angle difference between the two satellites
        excl_angle (float): The angle difference threshold

    Returns:
        list[tuple[datetime.datetime, datetime.datetime]]: List of tuples containing the start and end time of the exclusion times
    """
    exclusion_times: list[tuple[datetime.datetime, datetime.datetime]] = []
    min = None
    max = None

    for time, angle in angle_diff:
        if angle < excl_angle:
            if min is None:
                min = time
            max = time
        elif min is not None:
            exclusion_times.append((min, max))  # type: ignore
            min = None

    if min is not None:
        exclusion_times.append((min, max))  # type: ignore

    return exclusion_times


def is_visible(
    satellite: EarthSatellite,
    GroundStation: GroundStation,
    time: datetime.datetime,
    visibility_threshold: float = 5.0,
) -> np.bool:
    """Check if the satellite is visible from the ground GroundStation at the given time

    Args:
        satellite (EarthSatellite): Satellite to check visibility for
        GroundStation (GroundStation): Ground GroundStation to check visibility from
        time (datetime.datetime): Time to check visibility at
        visibility_threshold (float, optional): The angle that defines the visiblity (in degrees). Defaults to 5.0.

    Returns:
        np.bool: _description_
    """

    ts = load.timescale()
    time_obj = ts.from_datetime(time)

    # Skyfield Topos object for ground GroundStation
    gs = GroundStation.get_sf_geo_position()

    diff = satellite - gs
    topocentric = diff.at(time_obj)
    altitude, _, _ = topocentric.altaz()

    return altitude.degrees > visibility_threshold  # type: ignore


class RequestService:
    # crud requests
    @staticmethod
    def get_rf_time_request(db: Session, request_id: UUID) -> RFRequest | None:
        try:
            req = db.exec(select(RFRequest).where(RFRequest.id == request_id)).first()
            if req is None:
                raise HTTPException(
                    status_code=404,
                    detail=f"RF Time Request with ID {request_id} not found",
                )
            return req
        except HTTPException:
            raise
        except SQLAlchemyError as e:
            db.rollback()
            logger.error(f"Error getting RF time request: {str(e)}")
            raise HTTPException(
                status_code=503,
                detail=f"Database error while getting RF time request: {str(e)}",
            )
        except Exception as e:
            logger.error(f"Error getting RF time request: {str(e)}")
            raise HTTPException(
                status_code=500,
                detail=f"Error getting RF time request: {str(e)}",
            )

    @staticmethod
    def get_contact_request(db: Session, request_id: UUID) -> ContactRequest | None:
        try:
            req = db.exec(
                select(ContactRequest).where(ContactRequest.id == request_id)
            ).first()
            if req is None:
                raise HTTPException(
                    status_code=404,
                    detail=f"Contact Request with ID {request_id} not found",
                )
            return req
        except HTTPException:
            raise
        except SQLAlchemyError as e:
            db.rollback()
            logger.error(f"Error getting contact request: {str(e)}")
            raise HTTPException(
                status_code=503,
                detail=f"Database error while getting contact request: {str(e)}",
            )
        except Exception as e:
            logger.error(f"Error getting contact request: {str(e)}")
            raise HTTPException(
                status_code=500,
                detail=f"Error getting contact request: {str(e)}",
            )

    @staticmethod
    def create_rf_request(
        db: Session,
        request: RFTimeRequestModel,
        current_user: UserModel,
    ) -> RFRequest:
        try:
            # Validate request data
            if not request.missionName:
                raise HTTPException(
                    status_code=400,
                    detail="Mission name cannot be empty",
                )
            if request.startTime >= request.endTime:
                raise HTTPException(
                    status_code=400,
                    detail="Start time must be before end time",
                )
            if (
                request.uplinkTime < 0
                or request.downlinkTime < 0
                or request.scienceTime < 0
            ):
                raise HTTPException(
                    status_code=400,
                    detail="Time requests cannot be negative",
                )
            if request.minimumNumberOfPasses is None:
                request.minimumNumberOfPasses = 1
            if request.minimumNumberOfPasses < 1:
                raise HTTPException(
                    status_code=400,
                    detail="Minimum number of passes must be at least 1",
                )

            # -------- RBAC + mission_id handling --------
            mission_id_to_use: int | None = None

            # Only system_admin + mission_admin can create
            if current_user.role == SYSTEM_ADMIN:
                # can set any mission_id (including None)
                mission_id_to_use = request.mission_id

            elif current_user.role == MISSION_ADMIN:
                # mission_admin → locked to their mission_id
                if current_user.mission_id is None:
                    raise HTTPException(
                        status_code=400,
                        detail="Current user has no mission_id assigned",
                    )

                if (
                    request.mission_id is not None
                    and request.mission_id != current_user.mission_id
                ):
                    raise HTTPException(
                        status_code=403,
                        detail="Mission admins can only create RF requests for their own mission",
                    )

                mission_id_to_use = current_user.mission_id

            else:
                # system_user + mission_user (and anything else) → no write access
                raise HTTPException(
                    status_code=403,
                    detail="Write access denied for RF requests",
                )


            # -------- build entity --------
            rf_request = RFRequest(
                mission=request.missionName,
                satellite_id=request.satelliteId,
                start_time=request.startTime,
                end_time=request.endTime,
                uplink_time_requested=request.uplinkTime,
                downlink_time_requested=request.downlinkTime,
                science_time_requested=request.scienceTime,
                min_passes=request.minimumNumberOfPasses or 1,
                priority=1,
                ground_station_id=None,  # Will be set by the scheduler
                contact_id=None,  # Will be set when scheduled
                scheduled=False,
                time_remaining=0,  # Will be calculated in __init__
                num_passes_remaining=request.minimumNumberOfPasses or 1,
                mission_id=mission_id_to_use,
            )

            # ensure utc timezone
            rf_request.start_time = rf_request.start_time.replace(
                tzinfo=datetime.timezone.utc
            )
            rf_request.end_time = rf_request.end_time.replace(
                tzinfo=datetime.timezone.utc
            )

            db.add(rf_request)
            db.commit()
            db.refresh(rf_request)
            return rf_request

        except HTTPException:
            raise
        except SQLAlchemyError as e:
            db.rollback()
            logger.error(f"Error creating RF request: {str(e)}")
            raise HTTPException(
                status_code=503,
                detail=f"Database error while creating RF request: {str(e)}",
            )
        except Exception as e:
            logger.error(f"Error creating RF request: {str(e)}")
            raise HTTPException(
                status_code=500,
                detail=f"Error creating RF request: {str(e)}",
            )

    @staticmethod
    def create_contact_request(
        db: Session,
        request: ContactRequestModel,
        current_user: UserModel,
    ) -> ContactRequest:
        try:
            # ---- validation ----
            if not request.missionName:
                raise HTTPException(
                    status_code=400,
                    detail="Mission name cannot be empty",
                )
            if request.aosTime >= request.losTime:
                raise HTTPException(
                    status_code=400,
                    detail="AOS time must be before LOS time",
                )
            if request.rfOnTime >= request.rfOffTime:
                raise HTTPException(
                    status_code=400,
                    detail="RF on time must be before RF off time",
                )

            # ---- RBAC + mission_id handling ----
            mission_id_to_use: int | None = None

            if current_user.role == SYSTEM_ADMIN:
                mission_id_to_use = request.mission_id  # system_admin can set any

            elif current_user.role == MISSION_ADMIN:
                if current_user.mission_id is None:
                    raise HTTPException(
                        status_code=400,
                        detail="Current user has no mission_id assigned",
                    )

                if (
                    request.mission_id is not None
                    and request.mission_id != current_user.mission_id
                ):
                    raise HTTPException(
                        status_code=403,
                        detail="Mission admins can only create contact requests for their own mission",
                    )

                mission_id_to_use = current_user.mission_id

            else:
                # system_user + mission_user: no write access
                raise HTTPException(
                    status_code=403,
                    detail="Write access denied for contact requests",
                )

            # ---- build entity ----
            contact_request = ContactRequest(
                mission=request.missionName,
                satellite_id=request.satelliteId,
                start_time=request.aosTime,
                end_time=request.losTime,
                ground_station_id=request.station_id,
                orbit=request.orbit,
                uplink=request.uplink,
                telemetry=request.telemetry,
                science=request.science,
                aos=request.aosTime,
                los=request.losTime,
                rf_on=request.rfOnTime,
                rf_off=request.rfOffTime,
                duration=int((request.losTime - request.aosTime).total_seconds()),
                priority=1,
                booking_id=None,
                scheduled=False,
                mission_id=mission_id_to_use,
            )

            db.add(contact_request)
            db.commit()
            db.refresh(contact_request)
            return contact_request

        except HTTPException:
            raise
        except SQLAlchemyError as e:
            db.rollback()
            logger.error(f"Error creating contact request: {str(e)}")
            raise HTTPException(
                status_code=503,
                detail=f"Database error while creating contact request: {str(e)}",
            )
        except Exception as e:
            logger.error(f"Error creating contact request: {str(e)}")
            raise HTTPException(
                status_code=500,
                detail=f"Error creating contact request: {str(e)}",
            )

    @staticmethod
    def update_rf_request(db: Session, request: RFTimeRequestModel) -> RFRequest:
        try:
            rf_request = RFRequest(**request.model_dump())
            db.add(rf_request)
            db.commit()
            db.refresh(rf_request)
            return rf_request
        except SQLAlchemyError as e:
            db.rollback()
            logger.error(f"Error updating RF request: {str(e)}")
            raise HTTPException(
                status_code=503,
                detail=f"Database error while updating RF request: {str(e)}",
            )
        except Exception as e:
            logger.error(f"Error updating RF request: {str(e)}")
            raise HTTPException(
                status_code=500,
                detail=f"Error updating RF request: {str(e)}",
            )

    @staticmethod
    def delete_rf_time_request(db: Session, request_id: UUID) -> None:
        try:
            request = db.exec(
                select(RFRequest).where(RFRequest.id == request_id)
            ).first()
            if request is None:
                raise HTTPException(
                    status_code=404,
                    detail=f"RF Time Request with ID {request_id} not found",
                )
            db.delete(request)
            db.commit()
            return None
        except HTTPException:
            raise
        except SQLAlchemyError as e:
            db.rollback()
            logger.error(f"Error deleting RF request: {str(e)}")
            raise HTTPException(
                status_code=503,
                detail=f"Database error while deleting RF request: {str(e)}",
            )
        except Exception as e:
            logger.error(f"Error deleting RF request: {str(e)}")
            raise HTTPException(
                status_code=500,
                detail=f"Error deleting RF request: {str(e)}",
            )

    @staticmethod
    def delete_contact_request(db: Session, request_id: UUID) -> None:
        try:
            request = db.exec(
                select(ContactRequest).where(ContactRequest.id == request_id)
            ).first()
            if request is None:
                raise HTTPException(
                    status_code=404,
                    detail=f"Contact Request with ID {request_id} not found",
                )
            db.delete(request)
            db.commit()
            return None
        except HTTPException:
            raise
        except SQLAlchemyError as e:
            db.rollback()
            logger.error(f"Error deleting contact request: {str(e)}")
            raise HTTPException(
                status_code=503,
                detail=f"Database error while deleting contact request: {str(e)}",
            )
        except Exception as e:
            logger.error(f"Error deleting contact request: {str(e)}")
            raise HTTPException(
                status_code=500,
                detail=f"Error deleting contact request: {str(e)}",
            )
            
    @staticmethod
    def get_all_transformed_requests(
        db: Session,
        current_user: UserModel,
    ) -> list[GeneralContactResponseModel]:
        try:
            # Re-use RBAC logic from get_all_requests
            all_requests = RequestService.get_all_requests(db, current_user)

            contacts: list[GeneralContactResponseModel] = []
            for request in all_requests:
                result = RequestService.transform_request_to_general(
                    db, request, current_user
                )
                if result is not None:
                    contacts.append(result)
            return contacts

        except SQLAlchemyError as e:
            db.rollback()
            logger.error(f"Error getting all transformed requests: {str(e)}")
            raise HTTPException(
                status_code=503,
                detail=f"Database error while getting all transformed requests: {str(e)}",
            )
        except Exception as e:
            logger.error(f"Error getting all transformed requests: {str(e)}")
            raise HTTPException(
                status_code=500,
                detail=f"Error getting all transformed requests: {str(e)}",
            )





    @staticmethod
    def get_all_requests(
        db: Session,
        current_user: UserModel,
    ) -> list[Request]:
        try:
            rf_stmt = select(RFRequest)
            c_stmt = select(ContactRequest)

            if is_system_role(current_user):
                # system_admin / system_user → see everything
                pass
            elif is_mission_role(current_user):
                # mission_admin / mission_user → only their mission
                if current_user.mission_id is None:
                    # safest: return empty; or raise 400
                    return []
                rf_stmt = rf_stmt.where(RFRequest.mission_id == current_user.mission_id)
                c_stmt = c_stmt.where(ContactRequest.mission_id == current_user.mission_id)
            else:
                # other roles → no visibility
                return []

            rf_requests: list[RFRequest] = list(db.exec(rf_stmt).all())
            c_requests: list[ContactRequest] = list(db.exec(c_stmt).all())
            return [*rf_requests, *c_requests]

        except SQLAlchemyError as e:
            db.rollback()
            logger.error(f"Error getting all requests: {str(e)}")
            raise HTTPException(
                status_code=503,
                detail=f"Database error while getting all requests: {str(e)}",
            )
        except Exception as e:
            logger.error(f"Error getting all requests: {str(e)}")
            raise HTTPException(
                status_code=500,
                detail=f"Error getting all requests: {str(e)}",
            )


    @staticmethod
    def transform_request_to_general(
        db: Session,
        request: Request,
        current_user: UserModel,
    ) -> GeneralContactResponseModel | None:
        if request.ground_station_id is None:
            gs = None
        else:
            gs = GroundStationService.get_ground_station(db, request.ground_station_id)
            if gs is None:
                logger.error(
                    f"Ground Station with ID {request.ground_station_id} not found"
                )
                raise HTTPException(
                    status_code=404,
                    detail=f"Ground Station with ID {request.ground_station_id} not found",
                )

        sat = SatelliteService.get_satellite(db, request.satellite_id, current_user)
        if sat is None:
            logger.error(f"Satellite with ID {request.satellite_id} not found")
            raise HTTPException(
                status_code=404,
                detail=f"Satellite with ID {request.satellite_id} not found",
            )

        return GeneralContactResponseModel(
            requestType="RFTime" if isinstance(request, RFRequest) else "Contact",
            id=request.id,
            mission=request.mission,
            satellite_name=sat.name,
            station_id=(
                -1 if request.ground_station_id is None else request.ground_station_id
            ),
            uplink=request.uplink if isinstance(request, ContactRequest) else 0,
            telemetry=(request.telemetry if isinstance(request, ContactRequest) else 0),
            science=request.science if isinstance(request, ContactRequest) else 0,
            startTime=request.start_time,
            endTime=request.end_time,
            duration=((request.end_time - request.start_time).total_seconds()),
            aos=request.aos if isinstance(request, ContactRequest) else None,
            rf_on=request.rf_on if isinstance(request, ContactRequest) else None,
            rf_off=request.rf_off if isinstance(request, ContactRequest) else None,
            los=request.los if isinstance(request, ContactRequest) else None,
            orbit=request.orbit if isinstance(request, ContactRequest) else None,
            mission_id=getattr(request, "mission_id", None),
        )

    @staticmethod
    def get_bookings(db: Session, current_user: UserModel) -> list[Booking]:
        try:
            # Get all requests with RBAC filtering
            requests = RequestService.get_all_requests(db, current_user)

            # Get ground stations once
            stations = list(GroundStationService.get_ground_stations(db))

            # Pass both to scheduler
            bookings = schedule_with_slots(requests, stations)

            return bookings

        except SQLAlchemyError as e:
            db.rollback()
            logger.error(f"Error getting bookings: {str(e)}")
            raise HTTPException(
                status_code=503,
                detail=f"Database error while getting bookings: {str(e)}",
            )

        except Exception as e:
            logger.error(f"Error getting bookings: {str(e)}")
            raise HTTPException(
                status_code=500,
                detail=f"Error getting bookings: {str(e)}",
            )

    @staticmethod
    def sample(
        db: Session,
        current_user: UserModel,
    ) -> list[GeneralContactResponseModel]:
        sats = SatelliteService.get_satellites(db, current_user)
        stations = GroundStationService.get_ground_stations(db)
        if len(sats) < 2 or len(stations) < 2:
            logger.error("Need at least 2 satellites and 2 ground stations to demo")
            raise HTTPException(
                status_code=400,
                detail="Need at least 2 satellites and 2 ground stations to demo",
            )
        requests: list[Request] = [
            RFRequest(
                mission="Mission 1",
                satellite_id=sats[0].id,
                start_time=datetime.datetime(2025, 3, 1, 0, 0, 0),
                end_time=datetime.datetime(2025, 3, 1, 1, 0, 0),
                uplink_time_requested=30,
                downlink_time_requested=30,
                science_time_requested=30,
                min_passes=1,
                priority=1,
                contact_id=uuid.uuid4(),
                num_passes_remaining=1,  # Set explicit integer value
            ),
            RFRequest(
                mission="Mission 2",
                satellite_id=sats[1].id,
                start_time=datetime.datetime(2025, 3, 1, 0, 0, 0),
                end_time=datetime.datetime(2025, 3, 1, 1, 0, 0),
                uplink_time_requested=30,
                downlink_time_requested=30,
                science_time_requested=30,
                min_passes=1,
                priority=1,
                contact_id=uuid.uuid4(),
                num_passes_remaining=1,  # Set explicit integer value
            ),
            ContactRequest(
                mission="Mission 4",
                satellite_id=sats[0].id,
                start_time=datetime.datetime(2025, 1, 1, 0, 0, 0),
                end_time=datetime.datetime(2025, 1, 1, 1, 0, 0),
                ground_station_id=stations[0].id,
                orbit=1,
                uplink=True,
                telemetry=True,
                science=True,
                aos=datetime.datetime(2025, 1, 1, 0, 0, 0),
                los=datetime.datetime(2025, 1, 1, 1, 0, 0),
                rf_on=datetime.datetime(2025, 1, 1, 0, 0, 0),
                rf_off=datetime.datetime(2025, 1, 1, 1, 0, 0),
                duration=30,
                priority=1,
                booking_id=None,
            ),
            ContactRequest(
                mission="Mission 5",
                satellite_id=sats[1].id,
                start_time=datetime.datetime(2025, 1, 1, 0, 0, 0),
                end_time=datetime.datetime(2025, 1, 1, 1, 0, 0),
                ground_station_id=stations[1].id,
                orbit=1,
                uplink=True,
                telemetry=True,
                science=True,
                aos=datetime.datetime(2025, 1, 1, 0, 0, 0),
                los=datetime.datetime(2025, 1, 1, 1, 0, 0),
                rf_on=datetime.datetime(2025, 1, 1, 0, 0, 0),
                rf_off=datetime.datetime(2025, 1, 1, 1, 0, 0),
                duration=30,
                priority=1,
                booking_id=None,
            ),
        ]
        contacts = []
        # commit requests to db
        for request in requests:
            db.add(request)
        db.commit()
        for request in requests:
            result = RequestService.transform_request_to_general(db, request, current_user)
            if result is not None:
                contacts.append(result)
        return contacts
    
    #New Code added by MD
    def list_pending_requests(self, mission_id=None):
        # TODO: return a list of Request objects with .id, .satellite, .window_start, .window_end
        return self._list_pending_from_db(mission_id)

    def list_existing_contacts(self):
        # TODO: return objects with .station_id, .aos, .los (scheduled contacts)
        return self._list_contacts_from_db()

    def get_request(self, request_id: int):
        # TODO: fetch by id
        return self._get_request_from_db(request_id)

    def create_contact_from_candidate(self, req, candidate):
        # TODO: persist and return a contact-like object with mission_name, satellite_name, station_name, aos/rf_on/rf_off/los
        return self._create_contact_in_db(req, candidate)

    def compose_contact_like(self, req, candidate):
        """Return a lightweight object with the fields used by _as_report, without saving."""
        class C:
            pass
        c = C()
        c.mission_name = getattr(req, "mission_name", "Mission")
        c.satellite_name = getattr(req.satellite, "name", "SAT")
        c.station_name = str(candidate.get("station_id"))
        c.aos = candidate["aos"]
        c.rf_on = candidate["rf_on"]
        c.rf_off = candidate["rf_off"]
        c.los = candidate["los"]
        return c
