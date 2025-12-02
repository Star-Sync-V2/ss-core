"""
Scheduler smoke tests:
- Station capacity + guard band
- Satellite exclusivity
- Exclusion cone conflict pipeline

Run with:
    cd ss-core
    source .venv/bin/activate   # if needed
    python schedule_smoke.py

Prereqs:
    - Backend running on http://localhost:8000
    - /api/v1/hello/initdb and /api/v1/hello/create_demo_data have been called
    - The TOKENS dict below is filled with valid JWTs
"""

import requests
from datetime import datetime, timedelta

# -------------------------------------------------------------------
# CONFIG
# -------------------------------------------------------------------

BASE_URL = "http://localhost:8000/api/v1"   # same style as your RBAC smoke
SCHEDULE_PATH = "/api/v1/schedule/compute"  # -> http://localhost:8000/api/v1/api/v1/schedule/compute

# 🔴 FILL THESE WITH YOUR REAL TOKENS
TOKENS = {
    "system_admin":  "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJzeXN0ZW1fYWRtaW4iLCJleHAiOjE3NjQ2NDk2MzJ9.uYZb-TNMT9ymPzti5X24nVHhGg90N6Ywz9mORceqq1s",
    "system_user":   "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJzeXN0ZW1fdXNlciIsImV4cCI6MTc2NDY0OTY4MH0.lesCNgi0g1l8MmZd4lOfWz4tqOajAz6HssGqxF2yYC0",
    "mission_admin": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJtaXNzaW9uX2FkbWluIiwiZXhwIjoxNzY0NjQ5NzAyfQ.eulbVyHRbNKQ27qvgVxdYOUyptnJoAQvqPVL7cZiTyE",
    "mission_user":  "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJtaXNzaW9uX3VzZXIiLCJleHAiOjE3NjQ2NDk3MjV9.4rzGHSX352DYWMP3WMiSZthoHDSMJ2Ry9AoN7fyr3i4",
}

MIN_GAP_SECONDS = 300  # 5-minute guard band

# -------------------------------------------------------------------
# Helpers
# -------------------------------------------------------------------

def headers_for(role: str) -> dict:
    return {
        "Authorization": f"Bearer {TOKENS[role]}",
        "Content-Type": "application/json",
    }


def call(method: str, path: str, role: str, json_body=None):
    url = BASE_URL + path
    resp = requests.request(method, url, headers=headers_for(role), json=json_body)
    return resp


def pretty_result(label: str, resp, expected=None):
    status = resp.status_code
    ok = expected is None or status in expected
    tag = "OK" if ok else "FAIL"
    print(f"[{label:<30}] -> {status:<3} {tag}")
    if not ok:
        try:
            print("  Response:", resp.text[:300])
        except Exception:
            pass


def parse_iso(dt_str: str) -> datetime:
    """
    Parse ISO 8601 with trailing 'Z' into aware datetime in UTC.
    """
    if dt_str.endswith("Z"):
        dt_str = dt_str[:-1] + "+00:00"
    return datetime.fromisoformat(dt_str)


def gap_ok(a_start: datetime, a_end: datetime, b_start: datetime, b_end: datetime) -> bool:
    """
    Mirror of scheduler._gap_ok logic:
    Two intervals are allowed if (a_end + GAP <= b_start) or (b_end + GAP <= a_start).
    """
    gap = timedelta(seconds=MIN_GAP_SECONDS)
    if (a_end + gap) <= b_start or (b_end + gap) <= a_start:
        return True
    return False


# -------------------------------------------------------------------
# Bootstrap
# -------------------------------------------------------------------

def bootstrap_sat_gs_mission():
    """
    Get:
      - at least one satellite
      - at least one ground station
      - mission_id from satellite (assumes demo data created)
    """
    role = "system_admin"

    # Satellites
    r_sat = call("GET", "/satellites/", role)
    r_sat.raise_for_status()
    sats = r_sat.json()
    if not sats:
        raise RuntimeError(
            "No satellites found. Call /api/v1/hello/initdb and /api/v1/hello/create_demo_data first."
        )

    sat_main = sats[0]
    sat_main_id = sat_main["id"]
    sat_main_mission_id = sat_main.get("mission_id", 1)

    sat_int = sats[1] if len(sats) > 1 else None  # for exclusion cone test

    # Ground stations
    r_gs = call("GET", "/gs/", role)
    r_gs.raise_for_status()
    gss = r_gs.json()
    if not gss:
        raise RuntimeError(
            "No ground stations found. Call /api/v1/hello/initdb and /api/v1/hello/create_demo_data first."
        )
    gs = gss[0]
    gs_id = gs["id"]

    print("\nBootstrap:")
    print(f"  main_satellite_id   = {sat_main_id}")
    print(f"  main_satellite_name = {sat_main['name']}")
    print(f"  mission_id          = {sat_main_mission_id}")
    print(f"  ground_station_id   = {gs_id}")
    if sat_int:
        print(f"  interfering_sat_id  = {sat_int['id']}")
        print(f"  interfering_sat_name= {sat_int['name']}")
    else:
        print("  interfering_sat     = <none> (only 1 sat in DB)")

    return sat_main, sat_int, sat_main_mission_id, gs_id


def create_rf_request(
    sat_id: str,
    mission_id: int,
    start_iso: str,
    end_iso: str,
    role: str = "system_admin",
    uplink: int = 600,
    downlink: int = 600,
    science: int = 150,
    min_passes: int = 1,
):
    body = {
        "missionName": "SMOKE_TEST_MISSION",
        "mission_id": mission_id,
        "satelliteId": sat_id,
        "startTime": start_iso,
        "endTime": end_iso,
        "uplinkTime": uplink,
        "downlinkTime": downlink,
        "scienceTime": science,
        "minimumNumberOfPasses": min_passes,
    }
    resp = call("POST", "/request/rf-time", role, json_body=body)
    pretty_result(f"POST /request/rf-time ({start_iso}–{end_iso})", resp, expected={200})
    if resp.status_code == 200:
        return resp.json()
    return None


def create_exclusion_cone(
    main_sat_id: str,
    gs_id: int,
    interfering_sat_name: str,
    role: str = "system_admin",
):
    body = {
        "mission": "SMOKE_TEST_MISSION",
        "angle_limit": 10.0,  # fairly generous
        "interfering_satellite": interfering_sat_name,
        "satellite_id": main_sat_id,
        "gs_id": gs_id,
    }
    resp = call("POST", "/excones/", role, json_body=body)
    pretty_result("POST /excones/ (smoke)", resp, expected={200})
    if resp.status_code == 200:
        return resp.json()
    return None


def compute_schedule(window_start: str, window_end: str, mission_id: int, role: str = "system_admin"):
    body = {
        "windowStart": window_start,
        "windowEnd": window_end,
        "missionId": mission_id,
    }
    resp = call("POST", SCHEDULE_PATH, role, json_body=body)
    pretty_result("POST /schedule/compute", resp, expected={200})
    if resp.status_code == 200:
        return resp.json()
    return None


# -------------------------------------------------------------------
# Smoke test 2: Station capacity + guard band
# -------------------------------------------------------------------

def smoke_station_capacity(main_sat, mission_id: int):
    print("\n=== SMOKE 2: Station capacity + guard band ===")

    # plan over this window
    W_START = "2025-12-02T00:00:00Z"
    W_END   = "2025-12-02T06:00:00Z"

    # two overlapping RF requests for the same satellite
    rf1 = create_rf_request(
        sat_id=main_sat["id"],
        mission_id=mission_id,
        start_iso="2025-12-02T01:00:00Z",
        end_iso="2025-12-02T04:00:00Z",
    )
    rf2 = create_rf_request(
        sat_id=main_sat["id"],
        mission_id=mission_id,
        start_iso="2025-12-02T02:00:00Z",
        end_iso="2025-12-02T05:00:00Z",
    )

    sched = compute_schedule(W_START, W_END, mission_id)
    if not sched:
        print("  [FAIL] compute_schedule returned no data")
        return

    schedule = sched.get("schedule", [])
    print(f"  Scheduled contacts: {len(schedule)}")

    # Group by station and ensure no contacts violate guard band
    by_station = {}
    for c in schedule:
        sid = c["groundStationId"]
        by_station.setdefault(sid, []).append(c)

    all_ok = True
    for sid, entries in by_station.items():
        print(f"  Checking station {sid} with {len(entries)} contacts...")
        entries_sorted = sorted(entries, key=lambda x: parse_iso(x["aos"]))
        for i in range(len(entries_sorted) - 1):
            a = entries_sorted[i]
            b = entries_sorted[i + 1]
            a_start = parse_iso(a["aos"])
            a_end   = parse_iso(a["los"])
            b_start = parse_iso(b["aos"])
            b_end   = parse_iso(b["los"])
            if not gap_ok(a_start, a_end, b_start, b_end):
                print("    [FAIL] Guard-band violation between:")
                print(f"       {a}")
                print(f"       {b}")
                all_ok = False

    if all_ok:
        print("  [PASS] No station guard-band violations found.")


# -------------------------------------------------------------------
# Smoke test 3: Satellite exclusivity (no double-booking sat)
# -------------------------------------------------------------------

def smoke_satellite_exclusivity(main_sat, mission_id: int):
    print("\n=== SMOKE 3: Satellite exclusivity (per-sat guard band) ===")

    # again, use a broad window
    W_START = "2025-12-02T00:00:00Z"
    W_END   = "2025-12-02T06:00:00Z"

    # create some more overlapping RF requests for the same satellite
    create_rf_request(
        sat_id=main_sat["id"],
        mission_id=mission_id,
        start_iso="2025-12-02T00:30:00Z",
        end_iso="2025-12-02T03:30:00Z",
    )
    create_rf_request(
        sat_id=main_sat["id"],
        mission_id=mission_id,
        start_iso="2025-12-02T02:30:00Z",
        end_iso="2025-12-02T05:30:00Z",
    )

    sched = compute_schedule(W_START, W_END, mission_id)
    if not sched:
        print("  [FAIL] compute_schedule returned no data")
        return

    schedule = sched.get("schedule", [])
    print(f"  Scheduled contacts: {len(schedule)}")

    # Group by satellite and ensure no contacts violate guard band
    by_sat = {}
    for c in schedule:
        sid = c["satelliteId"]
        by_sat.setdefault(sid, []).append(c)

    all_ok = True
    for sid, entries in by_sat.items():
        print(f"  Checking satellite {sid} with {len(entries)} contacts...")
        entries_sorted = sorted(entries, key=lambda x: parse_iso(x["aos"]))
        for i in range(len(entries_sorted) - 1):
            a = entries_sorted[i]
            b = entries_sorted[i + 1]
            a_start = parse_iso(a["aos"])
            a_end   = parse_iso(a["los"])
            b_start = parse_iso(b["aos"])
            b_end   = parse_iso(b["los"])
            if not gap_ok(a_start, a_end, b_start, b_end):
                print("    [FAIL] Satellite guard-band violation between:")
                print(f"       {a}")
                print(f"       {b}")
                all_ok = False

    if all_ok:
        print("  [PASS] No per-satellite guard-band violations found.")


# -------------------------------------------------------------------
# Smoke test 4: Exclusion cone pipeline
# -------------------------------------------------------------------

def smoke_exclusion_cone(main_sat, int_sat, mission_id: int, gs_id: int):
    print("\n=== SMOKE 4: Exclusion cone conflicts pipeline ===")

    if int_sat is None:
        print("  [SKIP] Only one satellite available; cannot create realistic exclusion cone.")
        return

    # wide window again
    W_START = "2025-12-02T00:00:00Z"
    W_END   = "2025-12-02T06:00:00Z"

    # create cone: main_sat vs int_sat on gs_id
    cone = create_exclusion_cone(
        main_sat_id=main_sat["id"],
        gs_id=gs_id,
        interfering_sat_name=int_sat["name"],
    )
    if not cone:
        print("  [FAIL] Could not create exclusion cone; cannot test pipeline.")
        return

    # RF request for main_sat that spans the window; if geometry lines up,
    # this may violate the cone.
    create_rf_request(
        sat_id=main_sat["id"],
        mission_id=mission_id,
        start_iso=W_START,
        end_iso=W_END,
        uplink=1800,
        downlink=1800,
        science=1800,
    )

    sched = compute_schedule(W_START, W_END, mission_id)
    if not sched:
        print("  [FAIL] compute_schedule returned no data")
        return

    conflicts = sched.get("conflicts", [])
    excl_conflicts = [c for c in conflicts if c.get("type") == "exclusion_cone"]

    print(f"  Total conflicts: {len(conflicts)}")
    print(f"  Exclusion-cone conflicts: {len(excl_conflicts)}")

    if excl_conflicts:
        print("  [PASS] Exclusion-cone conflict(s) detected:")
        for c in excl_conflicts[:3]:
            print("    ", c)
    else:
        print("  [WARN] No exclusion_cone conflicts detected.")
        print("         This can happen if satellite geometry doesn't produce a close approach")
        print("         in this window. Pipeline still exercised (no crashes).")


# -------------------------------------------------------------------
# main
# -------------------------------------------------------------------

def main():
    try:
        main_sat, int_sat, mission_id, gs_id = bootstrap_sat_gs_mission()
    except Exception as e:
        print("Bootstrap failed:", e)
        return

    smoke_station_capacity(main_sat, mission_id)
    smoke_satellite_exclusivity(main_sat, mission_id)
    smoke_exclusion_cone(main_sat, int_sat, mission_id, gs_id)


if __name__ == "__main__":
    main()
