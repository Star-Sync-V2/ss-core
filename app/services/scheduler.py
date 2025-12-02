# ss-core/app/services/scheduler.py

from __future__ import annotations
from uuid import UUID
import logging
from fastapi import HTTPException, status
from sqlmodel import Session, select
from fastapi import HTTPException, status
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
from uuid import UUID
import logging

from sqlmodel import Session, select

from app.entities.Request import RFRequest, ContactRequest
from app.entities.Satellite import Satellite
from app.entities.GroundStation import GroundStation
from app.entities.Visibility import Visibility
from app.entities.ExclusionCone import ExclusionCone

from app.services.request import RequestService, angle_diff, get_excl_times
from app.services.ground_station import GroundStationService
from app.services.satellite import SatelliteService
from app.services.exclusion_cone import ExclusionConeService
from app.models.user import UserModel

logger = logging.getLogger(__name__)

MIN_GAP = timedelta(minutes=5)          # guard band between contacts
MIN_CONTACT_SECONDS = 60               # ignore ultra-short contacts


from datetime import datetime, timedelta, timezone
# (you already had datetime/timedelta; just ensure timezone is imported)


def _to_utc(dt: datetime) -> datetime:
    """
    Normalize any datetime (naive or timezone-aware) to *timezone-aware* UTC.

    - If dt is naive: assume it's UTC and attach tzinfo=UTC
    - If dt is aware: convert to UTC
    """
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)




@dataclass
class CandidateContact:
    """
    Internal candidate contact before acceptance.
    """
    request: RFRequest | ContactRequest
    request_type: str           # "RF" or "Contact"
    satellite: Satellite
    ground_station: GroundStation
    aos: datetime
    los: datetime
    rf_on: datetime
    rf_off: datetime
    duration: float             # seconds
    priority: int               # request priority
    base_score: float           # static greedy score used for sorting


@dataclass
class ScheduledContact:
    """
    Final scheduled contact returned in API response.
    """
    request_id: UUID
    request_type: str
    mission_id: Optional[int]
    satellite_id: UUID
    ground_station_id: int
    aos: datetime
    los: datetime
    rf_on: datetime
    rf_off: datetime
    duration: float
    priority: int


@dataclass
class Conflict:
    """
    Conflict description for UI / analysis.
    """
    type: str                   # "station_overlap", "satellite_overlap", "exclusion_cone"
    station_id: Optional[int]
    satellite_ids: List[UUID]
    start: datetime
    end: datetime
    details: str


class SchedulerService:
    """
    Greedy, constraint-aware scheduler.

    - Uses RequestService.get_all_requests for mission-scoped input
    - Generates candidate contacts from:
        * ContactRequest (fixed AOS/LOS)
        * RFRequest via visibility windows (stub now, SGP4-ready later)
    - Hard constraints:
        * 1 contact per station at a time (+5 min guard band)
        * 1 contact per satellite at a time (+5 min guard band)
    - Exclusion cone conflicts detected via angle_diff / get_excl_times
    """

    def __init__(self, db: Session, current_user: UserModel):
        self.db = db
        self.current_user = current_user
        self.gs_service = GroundStationService()
        # SatelliteService & others are class-based, so we use their static methods

    # -------------------------------------------------------------------------
    # Public API
    # -------------------------------------------------------------------------

    def compute_schedule(
        self,
        window_start: datetime,
        window_end: datetime,
        mission_id: Optional[int] = None,
    ) -> Dict[str, Any]:
# ✅ normalize inputs to UTC-aware
        window_start = _to_utc(window_start)
        window_end = _to_utc(window_end)

    # (keep your existing validation too)
        if window_end <= window_start:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="windowEnd must be strictly greater than windowStart",
            )
        """
        Main entry point for /schedule/compute.

        Returns a JSON-serializable dict with:
          - window
          - schedule[]
          - conflicts[]
          - metrics{}
        """
        logger.info(
            "Scheduler starting: window_start=%s window_end=%s mission_id=%s user=%s",
            window_start,
            window_end,
            mission_id,
            self.current_user.id,
        )

        # 1) Load all relevant inputs (requests, satellites, ground stations, cones)
        rf_requests, contact_requests = self._load_requests(window_start, window_end, mission_id)
        satellites = self._load_satellites(rf_requests, contact_requests)
        ground_stations = self._load_ground_stations()
        exclusion_cones = self._load_exclusion_cones(mission_id)

        # 2) Build candidate contacts
        candidates: List[CandidateContact] = []
        candidates.extend(
            self._build_candidates_for_contacts(contact_requests, satellites, ground_stations)
        )
        candidates.extend(
            self._build_candidates_for_rf_requests(
                rf_requests,
                satellites,
                ground_stations,
                window_start,
                window_end,
            )
        )

        if not candidates:
            logger.info("Scheduler: no candidates built for given window")
            return {
                "window": {"start": window_start, "end": window_end},
                "schedule": [],
                "conflicts": [],
                "metrics": {
                    "numRequests": len(rf_requests) + len(contact_requests),
                    "numCandidates": 0,
                    "numScheduled": 0,
                    "numDeferred": len(rf_requests) + len(contact_requests),
                    "fulfillmentRate": 0.0,
                },
            }

        # 3) Sort candidates by descending base_score, then earlier AOS
        candidates.sort(key=lambda c: (-c.base_score, c.aos))

        # 4) Greedy acceptance with constraint checks
        schedule: List[ScheduledContact] = []
        station_timeline: Dict[int, List[ScheduledContact]] = {}
        sat_timeline: Dict[UUID, List[ScheduledContact]] = {}

        # Track per-request fulfillment for RFRequests
        rf_remaining_time: Dict[UUID, float] = {
            r.id: max(
                r.uplink_time_requested,
                r.downlink_time_requested,
                r.science_time_requested,
            )
            for r in rf_requests
        }
        rf_passes_remaining: Dict[UUID, int] = {r.id: r.min_passes for r in rf_requests}

        for cand in candidates:
            # Check if request still needs service
            if isinstance(cand.request, RFRequest):
                rem_time = rf_remaining_time.get(cand.request.id, 0.0)
                rem_passes = rf_passes_remaining.get(cand.request.id, 0)
                if rem_time <= 0 or rem_passes <= 0:
                    continue

            # Hard constraints: per-station and per-satellite timelines
            if not self._is_feasible(cand, station_timeline, sat_timeline):
                continue

            # Accept candidate
            accepted = self._accept_candidate(
                cand,
                rf_remaining_time,
                rf_passes_remaining,
            )
            schedule.append(accepted)

            station_timeline.setdefault(accepted.ground_station_id, []).append(accepted)
            sat_timeline.setdefault(accepted.satellite_id, []).append(accepted)

        # 5) Sort timelines for consistency
        for sid in station_timeline:
            station_timeline[sid].sort(key=lambda c: c.aos)
        for sid in sat_timeline:
            sat_timeline[sid].sort(key=lambda c: c.aos)

        # 6) Detect conflicts (sanity + exclusion cones)
        conflicts: List[Conflict] = []
        conflicts.extend(self._detect_station_and_sat_conflicts(schedule))
        conflicts.extend(
            self._detect_exclusion_conflicts(
                schedule,
                satellites,
                ground_stations,
                exclusion_cones,
                window_start,
                window_end,
            )
        )

        # 7) Build metrics
        num_requests = len(rf_requests) + len(contact_requests)
        num_scheduled = len(schedule)
        num_deferred = max(0, num_requests - num_scheduled)
        fulfillment_rate = float(num_scheduled) / num_requests if num_requests else 0.0

        metrics = {
            "numRequests": num_requests,
            "numCandidates": len(candidates),
            "numScheduled": num_scheduled,
            "numDeferred": num_deferred,
            "fulfillmentRate": fulfillment_rate,
        }

        logger.info(
            "Scheduler done: scheduled=%d deferred=%d fulfillment=%.3f",
            num_scheduled,
            num_deferred,
            fulfillment_rate,
        )

        # 8) Return JSON-serializable response
        return {
            "window": {"start": window_start, "end": window_end},
            "schedule": [self._scheduled_to_dict(c) for c in schedule],
            "conflicts": [self._conflict_to_dict(c) for c in conflicts],
            "metrics": metrics,
        }

    # -------------------------------------------------------------------------
    # Loading helpers
    # -------------------------------------------------------------------------

    def _load_requests(
        self,
        window_start: datetime,
        window_end: datetime,
        mission_id: Optional[int],
    ) -> tuple[List[RFRequest], List[ContactRequest]]:
        """
        Use RequestService.get_all_requests with RBAC, then filter by time window & mission.
        All comparisons are done in UTC-aware datetimes.
        """
        ws = _to_utc(window_start)
        we = _to_utc(window_end)

        all_requests = RequestService.get_all_requests(self.db, self.current_user)

        rf_reqs: List[RFRequest] = []
        contact_reqs: List[ContactRequest] = []

        for req in all_requests:
            rs = _to_utc(req.start_time)
            re = _to_utc(req.end_time)

            # Time window intersection
            if re < ws or rs > we:
                continue

            # Mission filter if provided
            if mission_id is not None:
                if getattr(req, "mission_id", None) != mission_id:
                    continue

            if isinstance(req, RFRequest):
                rf_reqs.append(req)
            elif isinstance(req, ContactRequest):
                contact_reqs.append(req)

        return rf_reqs, contact_reqs
 

    def _load_satellites(
        self,
        rf_requests: List[RFRequest],
        contact_requests: List[ContactRequest],
    ) -> Dict[UUID, Satellite]:
        sat_ids = {r.satellite_id for r in rf_requests} | {
            c.satellite_id for c in contact_requests
        }

        satellites: Dict[UUID, Satellite] = {}
        for sid in sat_ids:
            sat = SatelliteService.get_satellite(self.db, sid, self.current_user)
            satellites[sid] = sat
        return satellites

    def _load_ground_stations(self) -> Dict[int, GroundStation]:
        stations = GroundStationService.get_ground_stations(self.db)
        return {gs.id: gs for gs in stations}

    def _load_exclusion_cones(
        self,
        mission_id: Optional[int],
    ) -> List[ExclusionCone]:
        cones = ExclusionConeService.get_exclusion_cones(self.db, self.current_user)
        if mission_id is not None:
            cones = [c for c in cones if c.mission_id == mission_id]
        return cones

    # -------------------------------------------------------------------------
    # Candidate building
    # -------------------------------------------------------------------------

    def _build_candidates_for_contacts(
        self,
        contact_requests: List[ContactRequest],
        satellites: Dict[UUID, Satellite],
        ground_stations: Dict[int, GroundStation],
    ) -> List[CandidateContact]:
        candidates: List[CandidateContact] = []

        for req in contact_requests:
            sat = satellites.get(req.satellite_id)
            gs = ground_stations.get(req.ground_station_id)

            if sat is None or gs is None:
                logger.warning(
                    "ContactRequest %s refers to missing sat or gs; skipping", req.id
                )
                continue

            aos = _to_utc(req.aos)
            los = _to_utc(req.los)
            rf_on = _to_utc(req.rf_on)
            rf_off = _to_utc(req.rf_off)

            if aos >= los:
                continue

            duration = (los - aos).total_seconds()
            if duration < MIN_CONTACT_SECONDS:
                continue

            base_score = float(req.priority) * 10.0 + duration / 60.0 + float(
                getattr(sat, "priority", 1)
            )

            candidates.append(
                CandidateContact(
                    request=req,
                    request_type="Contact",
                    satellite=sat,
                    ground_station=gs,
                    aos=aos,
                    los=los,
                    rf_on=rf_on,
                    rf_off=rf_off,
                    duration=duration,
                    priority=req.priority,
                    base_score=base_score,
                )
            )

        return candidates

    def _build_candidates_for_rf_requests(
        self,
        rf_requests: List[RFRequest],
        satellites: Dict[UUID, Satellite],
        ground_stations: Dict[int, GroundStation],
        window_start: datetime,
        window_end: datetime,
    ) -> List[CandidateContact]:
        """
        Build candidates by intersecting RF request windows with visibility windows.
        All datetime comparisons are done in UTC-aware datetimes.
        """
        horizon_start = _to_utc(window_start)
        horizon_end = _to_utc(window_end)

        candidates: List[CandidateContact] = []

        for req in rf_requests:
            sat = satellites.get(req.satellite_id)
            if sat is None:
                logger.warning("RFRequest %s refers to missing sat; skipping", req.id)
                continue

            max_required = max(
                req.uplink_time_requested,
                req.downlink_time_requested,
                req.science_time_requested,
            )
            if max_required <= 0:
                continue

            req_start = _to_utc(req.start_time)
            req_end = _to_utc(req.end_time)

            req_window_start = max(req_start, horizon_start)
            req_window_end = min(req_end, horizon_end)
            if req_window_start >= req_window_end:
                continue

            if req.ground_station_id is not None:
                target_stations = (
                    [ground_stations[req.ground_station_id]]
                    if req.ground_station_id in ground_stations
                    else []
                )
            else:
                target_stations = list(ground_stations.values())

            for gs in target_stations:
                try:
                    vis_list: List[Visibility] = self.gs_service.get_visibilities(
                        satellite=sat,
                        gs=gs,
                        start=req_window_start,
                        end=req_window_end,
                    )
                except Exception as e:
                    logger.error(
                        "Error computing visibility for sat=%s gs=%s: %s",
                        sat.id,
                        gs.id,
                        str(e),
                    )
                    continue

                for vis in vis_list:
                    vis_start = _to_utc(vis.start)
                    vis_end = _to_utc(vis.end)

                    aos = max(vis_start, req_window_start)
                    los = min(vis_end, req_window_end)
                    if aos >= los:
                        continue

                    duration = (los - aos).total_seconds()
                    if duration < MIN_CONTACT_SECONDS:
                        continue

                    rf_on = aos + timedelta(seconds=30)
                    rf_off = los - timedelta(seconds=30)
                    if rf_on >= rf_off:
                        rf_on = aos
                        rf_off = los

                    base_score = (
                        float(req.priority) * 10.0
                        + float(getattr(sat, "priority", 1)) * 5.0
                        + duration / 60.0
                    )

                    candidates.append(
                        CandidateContact(
                            request=req,
                            request_type="RF",
                            satellite=sat,
                            ground_station=gs,
                            aos=aos,
                            los=los,
                            rf_on=rf_on,
                            rf_off=rf_off,
                            duration=duration,
                            priority=req.priority,
                            base_score=base_score,
                        )
                    )

        return candidates

    # -------------------------------------------------------------------------
    # Greedy acceptance & constraints
    # -------------------------------------------------------------------------

    def _is_feasible(
        self,
        cand: CandidateContact,
        station_timeline: Dict[int, List[ScheduledContact]],
        sat_timeline: Dict[UUID, List[ScheduledContact]],
    ) -> bool:
        """
        Check:
          - no overlapping contacts on same station (+ MIN_GAP)
          - no overlapping contacts for same satellite (+ MIN_GAP)
        """
        gs_id = cand.ground_station.id
        sat_id = cand.satellite.id

        # station constraint
        for existing in station_timeline.get(gs_id, []):
            if not self._gap_ok(cand.aos, cand.los, existing.aos, existing.los):
                return False

        # satellite constraint
        for existing in sat_timeline.get(sat_id, []):
            if not self._gap_ok(cand.aos, cand.los, existing.aos, existing.los):
                return False

        return True

    @staticmethod
    def _gap_ok(
        a_start: datetime,
        a_end: datetime,
        b_start: datetime,
        b_end: datetime,
    ) -> bool:
        """
        Two intervals are in conflict if they overlap within the guard band.
        """
        # a overlaps b if not (a_end + gap <= b_start or b_end + gap <= a_start)
        if (a_end + MIN_GAP) <= b_start or (b_end + MIN_GAP) <= a_start:
            return True
        return False

    def _accept_candidate(
        self,
        cand: CandidateContact,
        rf_remaining_time: Dict[UUID, float],
        rf_passes_remaining: Dict[UUID, int],
    ) -> ScheduledContact:
        """
        Convert CandidateContact into ScheduledContact, update RFRequest bookkeeping.
        """
        if isinstance(cand.request, RFRequest):
            rid = cand.request.id
            used = min(cand.duration, rf_remaining_time.get(rid, 0.0))
            rf_remaining_time[rid] = max(0.0, rf_remaining_time.get(rid, 0.0) - used)

            # Count this as a pass if we booked at least 1 second
            if used > 0:
                rf_passes_remaining[rid] = max(
                    0, rf_passes_remaining.get(rid, cand.request.min_passes) - 1
                )

        sched = ScheduledContact(
            request_id=cand.request.id,
            request_type=cand.request_type,
            mission_id=getattr(cand.request, "mission_id", None),
            satellite_id=cand.satellite.id,
            ground_station_id=cand.ground_station.id,
            aos=cand.aos,
            los=cand.los,
            rf_on=cand.rf_on,
            rf_off=cand.rf_off,
            duration=cand.duration,
            priority=cand.priority,
        )
        return sched

    # -------------------------------------------------------------------------
    # Conflict detection
    # -------------------------------------------------------------------------

    def _detect_station_and_sat_conflicts(
        self,
        schedule: List[ScheduledContact],
    ) -> List[Conflict]:
        """
        Re-scan schedule for overlaps (should be none if greedy works,
        but this gives you explicit conflict objects for the UI / report).
        """
        conflicts: List[Conflict] = []

        # Station-based
        by_station: Dict[int, List[ScheduledContact]] = {}
        for c in schedule:
            by_station.setdefault(c.ground_station_id, []).append(c)

        for sid, entries in by_station.items():
            entries_sorted = sorted(entries, key=lambda x: x.aos)
            for i in range(len(entries_sorted) - 1):
                a = entries_sorted[i]
                b = entries_sorted[i + 1]
                if not self._gap_ok(a.aos, a.los, b.aos, b.los):
                    conflicts.append(
                        Conflict(
                            type="station_overlap",
                            station_id=sid,
                            satellite_ids=[a.satellite_id, b.satellite_id],
                            start=max(a.aos, b.aos),
                            end=min(a.los, b.los),
                            details="Two contacts overlap or violate guard band on same station",
                        )
                    )

        # Satellite-based
        by_sat: Dict[UUID, List[ScheduledContact]] = {}
        for c in schedule:
            by_sat.setdefault(c.satellite_id, []).append(c)

        for sid, entries in by_sat.items():
            entries_sorted = sorted(entries, key=lambda x: x.aos)
            for i in range(len(entries_sorted) - 1):
                a = entries_sorted[i]
                b = entries_sorted[i + 1]
                if not self._gap_ok(a.aos, a.los, b.aos, b.los):
                    conflicts.append(
                        Conflict(
                            type="satellite_overlap",
                            station_id=None,
                            satellite_ids=[sid],
                            start=max(a.aos, b.aos),
                            end=min(a.los, b.los),
                            details="Satellite scheduled in overlapping windows",
                        )
                    )

        return conflicts

    def _detect_exclusion_conflicts(
        self,
        schedule: List[ScheduledContact],
        satellites: Dict[UUID, Satellite],
        ground_stations: Dict[int, GroundStation],
        exclusion_cones: List[ExclusionCone],
        window_start: datetime,
        window_end: datetime,
    ) -> List[Conflict]:
        """
        For each exclusion cone, compute times when the two satellites are
        within the forbidden angle over that ground station. Then mark any
        scheduled contacts that overlap those intervals.
        """
        conflicts: List[Conflict] = []

        if not exclusion_cones:
            return conflicts

        # Index schedule by (satellite_id, station_id)
        by_sat_and_station: Dict[tuple[UUID, int], List[ScheduledContact]] = {}
        for c in schedule:
            key = (c.satellite_id, c.ground_station_id)
            by_sat_and_station.setdefault(key, []).append(c)

        # Also index satellites by name for "interfering_satellite"
        sat_by_name: Dict[str, Satellite] = {}
        for sat in satellites.values():
            # use exact name string; you can later normalize if needed
            sat_by_name[sat.name] = sat

        for cone in exclusion_cones:
            sat_main = satellites.get(cone.satellite_id)
            sat_interfering = sat_by_name.get(cone.interfering_satellite)
            gs = ground_stations.get(cone.gs_id)

            if sat_main is None or sat_interfering is None or gs is None:
                continue

            # EarthSatellite objects from your entity helpers
            try:
                sat_main_sf = sat_main.get_sf_sat()
                sat_int_sf = sat_interfering.get_sf_sat()
                gs_pos = gs.get_sf_geo_position()
            except Exception as e:
                logger.error(
                    "Error building SF objects for exclusion cone %s: %s",
                    cone.id,
                    str(e),
                )
                continue

            # 1) angle over time
            try:
                angles = angle_diff(
                    window_start,
                    window_end,
                    sat_main_sf,
                    sat_int_sf,
                    gs_pos,
                )
                excl_windows = get_excl_times(angles, cone.angle_limit)
            except Exception as e:
                logger.error(
                    "Error computing exclusion windows for cone %s: %s",
                    cone.id,
                    str(e),
                )
                continue

            if not excl_windows:
                continue

            # 2) For any scheduled contact of main sat on this GS, check overlap
            key = (cone.satellite_id, cone.gs_id)
            contacts_here = by_sat_and_station.get(key, [])
            for contact in contacts_here:
                for (excl_start, excl_end) in excl_windows:
                    if excl_end < contact.aos or excl_start > contact.los:
                        continue
                    overlap_start = max(excl_start, contact.aos)
                    overlap_end = min(excl_end, contact.los)
                    if overlap_start < overlap_end:
                        conflicts.append(
                            Conflict(
                                type="exclusion_cone",
                                station_id=cone.gs_id,
                                satellite_ids=[contact.satellite_id],
                                start=overlap_start,
                                end=overlap_end,
                                details=(
                                    f"Contact violates exclusion cone with interfering "
                                    f"satellite '{cone.interfering_satellite}' "
                                    f"angle_limit={cone.angle_limit} deg"
                                ),
                            )
                        )

        return conflicts

    # -------------------------------------------------------------------------
    # Serialization helpers
    # -------------------------------------------------------------------------

    @staticmethod
    def _scheduled_to_dict(c: ScheduledContact) -> Dict[str, Any]:
        return {
            "requestId": str(c.request_id),
            "requestType": c.request_type,
            "missionId": c.mission_id,
            "satelliteId": str(c.satellite_id),
            "groundStationId": c.ground_station_id,
            "aos": c.aos,
            "rfOn": c.rf_on,
            "rfOff": c.rf_off,
            "los": c.los,
            "duration": c.duration,
            "priority": c.priority,
        }

    @staticmethod
    def _conflict_to_dict(conf: Conflict) -> Dict[str, Any]:
        return {
            "type": conf.type,
            "stationId": conf.station_id,
            "satelliteIds": [str(sid) for sid in conf.satellite_ids],
            "start": conf.start,
            "end": conf.end,
            "details": conf.details,
        }
