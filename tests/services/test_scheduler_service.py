import uuid
from datetime import datetime, timedelta, timezone

from app.services.scheduler import (
    SchedulerService,
    CandidateContact,
    ScheduledContact,
    MIN_GAP,
)
from app.entities.Request import RFRequest, ContactRequest
from app.entities.Satellite import Satellite
from app.entities.GroundStation import GroundStation
from app.entities.Visibility import Visibility


class DummyUser:
    def __init__(self, role: str = "system_admin", mission_id: int | None = None):
        self.id = uuid.uuid4()
        self.role = role
        self.mission_id = mission_id


def _utc(year, month, day, hour, minute=0, second=0):
    return datetime(year, month, day, hour, minute, second, tzinfo=timezone.utc)


def make_satellite(name: str = "SAT-1", priority: int = 1) -> Satellite:
    return Satellite(
        name=name,
        tle="SCISAT 1\n1 27858U 03036A   24298.42572809  .00002329  00000+0  31378-3 0  9994\n2 27858  73.9300 283.7690 0006053 131.3701 228.7996 14.79804256142522",
        uplink=40.0,
        telemetry=100.0,
        science=100.0,
        priority=priority,
    )


def make_ground_station(gs_id: int = 1, name: str = "GS-1") -> GroundStation:
    return GroundStation(
        id=gs_id,
        name=name,
        lat=45.0,
        lon=-75.0,
        height=100.0,
        mask=5,
        uplink=40.0,
        downlink=100.0,
        science=100.0,
    )


def test_gap_ok_non_overlapping():
    start_a = _utc(2025, 1, 1, 0, 0)
    end_a = start_a + timedelta(minutes=10)

    # Second contact starts after MIN_GAP from end_a → should be OK
    start_b = end_a + MIN_GAP + timedelta(seconds=1)
    end_b = start_b + timedelta(minutes=10)

    assert SchedulerService._gap_ok(start_a, end_a, start_b, end_b)
    assert SchedulerService._gap_ok(start_b, end_b, start_a, end_a)


def test_gap_ok_conflicting():
    start_a = _utc(2025, 1, 1, 0, 0)
    end_a = start_a + timedelta(minutes=10)

    # Second contact starts too close (inside guard band) → NOT OK
    start_b = end_a + MIN_GAP - timedelta(seconds=1)
    end_b = start_b + timedelta(minutes=10)

    assert not SchedulerService._gap_ok(start_a, end_a, start_b, end_b)
    assert not SchedulerService._gap_ok(start_b, end_b, start_a, end_a)


def test_accept_candidate_updates_rf_remaining_and_passes():
    dummy_user = DummyUser()
    scheduler = SchedulerService(db=None, current_user=dummy_user)

    rf_req = RFRequest(
        mission="TestMission",
        satellite_id=uuid.uuid4(),
        start_time=_utc(2025, 1, 1, 0, 0),
        end_time=_utc(2025, 1, 1, 1, 0),
        uplink_time_requested=600,
        downlink_time_requested=0,
        science_time_requested=0,
        min_passes=2,
        priority=1,
        contact_id=None,
        ground_station_id=None,
    )

    sat = make_satellite(priority=3)
    gs = make_ground_station(1, "GS-1")

    cand = CandidateContact(
        request=rf_req,
        request_type="RF",
        satellite=sat,
        ground_station=gs,
        aos=_utc(2025, 1, 1, 0, 10),
        los=_utc(2025, 1, 1, 0, 25),  # 15 min = 900 s
        rf_on=_utc(2025, 1, 1, 0, 11),
        rf_off=_utc(2025, 1, 1, 0, 24),
        duration=900.0,
        priority=rf_req.priority,
        base_score=1.0,
    )

    rf_remaining = {rf_req.id: 600.0}
    rf_passes_remaining = {rf_req.id: 2}

    scheduled = scheduler._accept_candidate(
        cand,
        rf_remaining_time=rf_remaining,
        rf_passes_remaining=rf_passes_remaining,
    )

    # used min(duration, remaining) = 600
    assert rf_remaining[rf_req.id] == 0.0
    # one pass consumed
    assert rf_passes_remaining[rf_req.id] == 1
    # scheduled contact fields look right
    assert isinstance(scheduled, ScheduledContact)
    assert scheduled.duration == cand.duration
    assert scheduled.ground_station_id == gs.id
    assert scheduled.satellite_id == sat.id


def test_build_candidates_for_rf_requests_uses_visibility_and_window():
    """
    Build candidates for a single RFRequest and single GS, with a stub
    visibility window. Expect exactly 1 candidate with intersected AOS/LOS.
    """
    dummy_user = DummyUser()
    scheduler = SchedulerService(db=None, current_user=dummy_user)

    # create satellite & GS first
    sat = make_satellite(name="SAT-1", priority=5)
    gs_obj = make_ground_station(1, "GS-1")

    satellites = {sat.id: sat}
    ground_stations = {gs_obj.id: gs_obj}

    rf_req = RFRequest(
        mission="TestMission",
        satellite_id=sat.id,
        start_time=_utc(2025, 1, 1, 0, 0),
        end_time=_utc(2025, 1, 1, 1, 0),
        uplink_time_requested=300,
        downlink_time_requested=0,
        science_time_requested=0,
        min_passes=1,
        priority=2,
        contact_id=None,
        ground_station_id=None,
    )

    # Stub visibility: 00:15–00:45
    vis_start = _utc(2025, 1, 1, 0, 15)
    vis_end = _utc(2025, 1, 1, 0, 45)

    # match actual SchedulerService.gs_service.get_visibilities signature
    def fake_get_visibilities(*, satellite, gs, start, end):
        assert satellite.id == sat.id
        assert gs.id == gs_obj.id
        return [Visibility(gs=gs_obj, sat=sat, start=vis_start, end=vis_end)]

    scheduler.gs_service.get_visibilities = fake_get_visibilities  # type: ignore[attr-defined]

    cands = scheduler._build_candidates_for_rf_requests(
        rf_requests=[rf_req],
        satellites=satellites,
        ground_stations=ground_stations,
        window_start=_utc(2025, 1, 1, 0, 0),
        window_end=_utc(2025, 1, 1, 2, 0),
    )

    assert len(cands) == 1
    cand = cands[0]

    assert cand.aos >= vis_start
    assert cand.los <= vis_end
    assert cand.duration > 0
    assert cand.ground_station.id == gs_obj.id
    assert cand.satellite.id == sat.id
    assert cand.request.id == rf_req.id
    assert cand.request_type == "RF"


def test_is_feasible_blocks_station_overlap():
    dummy_user = DummyUser()
    scheduler = SchedulerService(db=None, current_user=dummy_user)

    sat = make_satellite("SAT-1")
    gs = make_ground_station(1, "GS-1")

    base_start = _utc(2025, 1, 1, 0, 0)
    base_end = base_start + timedelta(minutes=10)

    existing = ScheduledContact(
        request_id=uuid.uuid4(),
        request_type="RF",
        mission_id=None,
        satellite_id=sat.id,
        ground_station_id=gs.id,
        aos=base_start,
        los=base_end,
        rf_on=base_start,
        rf_off=base_end,
        duration=(base_end - base_start).total_seconds(),
        priority=1,
    )

    station_timeline = {gs.id: [existing]}
    sat_timeline = {sat.id: [existing]}

    # Candidate overlapping in time → infeasible
    cand_overlap = CandidateContact(
        request=RFRequest(
            mission="M",
            satellite_id=sat.id,
            start_time=_utc(2025, 1, 1, 0, 5),
            end_time=_utc(2025, 1, 1, 0, 20),
            uplink_time_requested=60,
            downlink_time_requested=0,
            science_time_requested=0,
            min_passes=1,
            priority=1,
            contact_id=None,
            ground_station_id=gs.id,
        ),
        request_type="RF",
        satellite=sat,
        ground_station=gs,
        aos=_utc(2025, 1, 1, 0, 5),
        los=_utc(2025, 1, 1, 0, 20),
        rf_on=_utc(2025, 1, 1, 0, 6),
        rf_off=_utc(2025, 1, 1, 0, 19),
        duration=900.0,
        priority=1,
        base_score=1.0,
    )

    assert not scheduler._is_feasible(
        cand_overlap,
        station_timeline=station_timeline,
        sat_timeline=sat_timeline,
    )

    # Candidate well separated with guard band → feasible
    sep_start = base_end + MIN_GAP + timedelta(seconds=1)
    sep_end = sep_start + timedelta(minutes=10)

    cand_ok = CandidateContact(
        request=cand_overlap.request,
        request_type="RF",
        satellite=sat,
        ground_station=gs,
        aos=sep_start,
        los=sep_end,
        rf_on=sep_start,
        rf_off=sep_end,
        duration=(sep_end - sep_start).total_seconds(),
        priority=1,
        base_score=1.0,
    )

    assert scheduler._is_feasible(
        cand_ok,
        station_timeline=station_timeline,
        sat_timeline=sat_timeline,
    )


def test_detect_exclusion_conflicts_empty_cones_returns_empty():
    """
    Sanity check: with no exclusion cones, we should get no exclusion conflicts.
    """
    dummy_user = DummyUser()
    scheduler = SchedulerService(db=None, current_user=dummy_user)

    sat = make_satellite("SAT-1")
    gs = make_ground_station(1, "GS-1")

    contact = ScheduledContact(
        request_id=uuid.uuid4(),
        request_type="Contact",
        mission_id=None,
        satellite_id=sat.id,
        ground_station_id=gs.id,
        aos=_utc(2025, 1, 1, 0, 0),
        los=_utc(2025, 1, 1, 0, 10),
        rf_on=_utc(2025, 1, 1, 0, 1),
        rf_off=_utc(2025, 1, 1, 0, 9),
        duration=600.0,
        priority=1,
    )

    conflicts = scheduler._detect_exclusion_conflicts(
        schedule=[contact],
        satellites={sat.id: sat},
        ground_stations={gs.id: gs},
        exclusion_cones=[],
        window_start=_utc(2025, 1, 1, 0, 0),
        window_end=_utc(2025, 1, 1, 1, 0),
    )

    assert conflicts == []
