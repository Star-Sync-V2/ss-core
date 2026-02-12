"""
RBAC + mission scoping smoke tests for core services.

Run with:
    cd ss-core
    source .venv/bin/activate   # if needed
    python smoke_test/rbac_smoke.py
"""

import requests
import json

BASE_URL = "http://localhost:8000/api/v1"

TOKENS = {
    "system_admin":  "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJzeXN0ZW1fYWRtaW4iLCJleHAiOjE3NzA5MzY0MTN9.C8-Jmx6uyxNmV5vdkw0CefrnM_-Vr6gbDP7gidZUBs0",
    "system_user":   "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJzeXN0ZW1fdXNlciIsImV4cCI6MTc3MDkzNjM5OH0.h0OOO5BYHCDwI3_tEW3sNHIPECqoIKfp5mco-C5m-Ac",
    "mission_admin": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJtaXNzaW9uX2FkbWluIiwiZXhwIjoxNzcwOTM2MzgyfQ.8LeMKaTUcKUeUc4uEljrNx0YD6HeX1c69dZnZJueuSM",
    "mission_user":  "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJtaXNzaW9uX3VzZXIiLCJleHAiOjE3NzA5MzYzNjN9.nzCPKmF4ubv7za05NkWj95bJJzwnV1GL_n6ODML0FqY",
}


ROLES = list(TOKENS.keys())


# ---------------------------
# Helpers
# ---------------------------
from datetime import datetime, timezone

MIN_GAP_SECONDS = 300  # 5 min

def parse_iso_z(s: str) -> datetime:
    # supports "2025-12-02T01:00:00Z"
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    return datetime.fromisoformat(s)

def assert_no_overlaps(schedule: list, *,
                       start_key="start_time",
                       end_key="end_time",
                       station_key="ground_station_id",
                       sat_key="satellite_id"):
    # group by station and by satellite
    def check_group(key):
        buckets = {}
        for c in schedule:
            buckets.setdefault(c.get(key), []).append(c)

        for k, items in buckets.items():
            items = sorted(items, key=lambda x: parse_iso_z(x[start_key]))
            for a, b in zip(items, items[1:]):
                a_end = parse_iso_z(a[end_key])
                b_start = parse_iso_z(b[start_key])
                if (a_end.timestamp() + MIN_GAP_SECONDS) > b_start.timestamp():
                    raise AssertionError(
                        f"Guard-band overlap on {key}={k}: "
                        f"{a[start_key]}–{a[end_key]} then {b[start_key]}–{b[end_key]}"
                    )

    check_group(station_key)
    check_group(sat_key)
    
    
def headers_for(role: str) -> dict:
    return {
        "Authorization": f"Bearer {TOKENS[role]}",
        "Content-Type": "application/json",
    }


def call(method: str, path: str, role: str, json_body=None):
    url = BASE_URL + path
    resp = requests.request(method, url, headers=headers_for(role), json=json_body)
    return resp


def pretty_result(role: str, method: str, path: str, resp, expected=None):
    status = resp.status_code
    label = "OK" if expected is None or status in expected else "FAIL"
    print(f"[{role:<12}] {method:<4} {path:<28} -> {status:<3} {label}")
    if label == "FAIL":
        try:
            print("  Response:", resp.text[:300])
        except Exception:
            pass


def get_me(role: str) -> dict:
    resp = call("GET", "/auth/users/me", role)
    resp.raise_for_status()
    return resp.json()


def bootstrap_all():
    """
    Use system_admin to fetch:
      - one satellite (id + mission_id)
      - one ground station (id)
    Assumes /hello/initdb and /hello/create_demo_data have been run.
    """
    role = "system_admin"

    # Satellites
    r_sat = call("GET", "/satellites/", role)
    r_sat.raise_for_status()
    sats = r_sat.json()
    if not sats:
        raise RuntimeError(
            "No satellites found. Hit /api/v1/hello/initdb then /api/v1/hello/create_demo_data first."
        )
    sat = sats[0]
    sat_id = sat["id"]
    mission_id = sat.get("mission_id", 1)

    # Ground stations
    r_gs = call("GET", "/gs/", role)
    r_gs.raise_for_status()
    gss = r_gs.json()
    if not gss:
        raise RuntimeError(
            "No ground stations found. Hit /api/v1/hello/initdb then /api/v1/hello/create_demo_data first."
        )
    gs_id = gss[0]["id"]

    print("\nBootstrap:")
    print(f"  satelliteId = {sat_id}")
    print(f"  mission_id  = {mission_id}")
    print(f"  gs_id       = {gs_id}\n")

    return sat_id, mission_id, gs_id


# ---------------------------
# Tests
# ---------------------------

def test_mission_list_and_scoping():
    print("\n=== GET /mission/ (RBAC + mission scoping) ===")
    for role in ROLES:
        resp = call("GET", "/mission/", role)
        pretty_result(role, "GET", "/mission/", resp, expected={200})
        if resp.status_code != 200:
            continue

        data = resp.json()
        # For mission roles, ensure only their mission is returned (if any)
        if role in ("mission_admin", "mission_user"):
            me = get_me(role)
            my_mission_id = me.get("mission_id")
            bad = [m for m in data if m.get("id") != my_mission_id]
            if bad:
                print(f"  [WARN] {role} sees missions not equal to mission_id={my_mission_id}: {bad}")
            else:
                print(f"  [PASS] {role} mission scoping looks correct (only mission_id={my_mission_id}).")


def test_rf_request_create_rbac(sat_id: str, mission_id: int):
    print("\n=== POST /request/rf-time (RBAC on create) ===")

    rf_body = {
        "missionName": "SCISAT",
        "mission_id": mission_id,
        "satelliteId": sat_id,
        "startTime": "2025-11-19T01:03:04Z",
        "endTime":   "2025-11-20T01:03:04Z",
        "uplinkTime": 600,
        "downlinkTime": 600,
        "scienceTime": 150,
        "minimumNumberOfPasses": 2,
    }

    EXPECTED = {
        "system_admin":  {200},
        "mission_admin": {200},
        "system_user":   {403},
        "mission_user":  {403},
    }

    for role in ROLES:
        resp = call("POST", "/request/rf-time", role, json_body=rf_body)
        pretty_result(role, "POST", "/request/rf-time", resp, expected=EXPECTED[role])


def test_request_list_scoping():
    print("\n=== GET /request/ (RBAC + mission scoping) ===")
    for role in ROLES:
        resp = call("GET", "/request/", role)
        pretty_result(role, "GET", "/request/", resp, expected={200})
        if resp.status_code != 200:
            continue

        data = resp.json()
        # For mission roles, ensure every request has mission_id == their mission
        if role in ("mission_admin", "mission_user"):
            me = get_me(role)
            my_mission_id = me.get("mission_id")
            bad = [r for r in data if r.get("mission_id") not in (None, my_mission_id)]
            # treat None as legacy / pre-mission_id data
            bad = [r for r in bad if r.get("mission_id") is not None]
            if bad:
                print(f"  [WARN] {role} sees requests with mission_id != {my_mission_id}:")
                print("        sample:", json.dumps(bad[:2], indent=2))
            else:
                print(f"  [PASS] {role} request mission scoping looks correct.")


def test_excone_create_rbac(sat_id: str, gs_id: int):
    print("\n=== POST /excones/ (RBAC on Exclusion Cones) ===")

    body = {
        "mission": "SCISAT",
        "angle_limit": 5.0,
        "interfering_satellite": "OTHER SAT",
        "satellite_id": sat_id,
        "gs_id": gs_id,
    }

    EXPECTED = {
        "system_admin":  {200},
        "system_user":   {403},
        "mission_admin": {200},
        "mission_user":  {403},
    }

    for role in ROLES:
        resp = call("POST", "/excones/", role, json_body=body)
        pretty_result(role, "POST", "/excones/", resp, expected=EXPECTED[role])


def test_excone_list_basic():
    print("\n=== GET /excones/ (visibility) ===")
    for role in ROLES:
        resp = call("GET", "/excones/", role)
        pretty_result(role, "GET", "/excones/", resp, expected={200})


def test_users_list_rbac():
    print("\n=== GET /users/ (User Management RBAC) ===")
    for role in ROLES:
        resp = call("GET", "/users/", role)
        expected = {200} if role == "system_admin" else {401, 403}
        pretty_result(role, "GET", "/users/", resp, expected=expected)

def test_satellites_basic_visibility():
    print("\n=== GET /satellites/ (basic visibility) ===")
    for role in ROLES:
        resp = call("GET", "/satellites/", role)
        # All roles should at least be able to read satellites
        pretty_result(role, "GET", "/satellites/", resp, expected={200})


def test_ground_stations_basic_visibility():
    print("\n=== GET /gs/ (basic visibility) ===")
    for role in ROLES:
        resp = call("GET", "/gs/", role)
        # Depending on your team's decision, mission_user may or may not be allowed.
        # We just assert "no 5xx", and 200/403 are both acceptable here.
        if resp.status_code >= 500:
            pretty_result(role, "GET", "/gs/", resp, expected={200})
        else:
            pretty_result(role, "GET", "/gs/", resp, expected={200, 401, 403})
            
            
def test_scheduler_basic(sat_id: str, mission_id: int):
    print("\n=== SCHEDULER BASIC  ===")

    rf1 = {
        "missionName": "SCISAT",
        "mission_id": mission_id,
        "satelliteId": sat_id,
        "startTime": "2025-12-02T01:00:00Z",
        "endTime": "2025-12-02T04:00:00Z",
        "uplinkTime": 600,
        "downlinkTime": 600,
        "scienceTime": 150,
        "minimumNumberOfPasses": 1,
    }
    rf2 = rf1.copy()
    rf2["startTime"] = "2025-12-02T02:00:00Z"
    rf2["endTime"]   = "2025-12-02T05:00:00Z"

    call("POST", "/request/rf-time", "system_admin", rf1)
    call("POST", "/request/rf-time", "system_admin", rf2)

    resp = call(
        "POST", "/schedule/compute", "system_admin",
        {
            "windowStart": "2025-12-02T00:00:00Z",
            "windowEnd": "2025-12-02T06:00:00Z",
            "missionId": mission_id,
        },
    )
    pretty_result("system_admin", "POST", "/schedule/compute", resp, {200})
    data = resp.json()

    print("  schedule keys:", list(data.keys()))

    schedule = data.get("schedule") or data.get("contacts") or []
    conflicts = data.get("conflicts") or []

    print("  Scheduled contacts:", len(schedule))
    print("  Conflicts:", len(conflicts))

    if not schedule:
        print("  [FAIL] No contacts scheduled at all")
        return

    # TODO: adjust these keys to your real payload fields
    try:
        assert_no_overlaps(
            schedule,
            start_key="startTime",     # <- change if needed
            end_key="endTime",         # <- change if needed
            station_key="gs_id",       # <- change if needed
            sat_key="satellite_id",    # <- change if needed
        )
        print("  [PASS] No station/satellite guard-band overlaps (5 min).")
    except Exception as e:
        print("  [FAIL]", e)

    # Determinism check
    resp2 = call(
        "POST", "/schedule/compute", "system_admin",
        {
            "windowStart": "2025-12-02T00:00:00Z",
            "windowEnd": "2025-12-02T06:00:00Z",
            "missionId": mission_id,
        },
    )
    if resp2.status_code == 200 and resp.json() == resp2.json():
        print("  [PASS] Scheduler deterministic")
    else:
        print("  [WARN] Scheduler output changed between runs")
def main():
    # Bootstrap: find a valid sat_id, mission_id, gs_id
    try:
        sat_id, mission_id, gs_id = bootstrap_all()
    except Exception as e:
        print("Bootstrap failed:", e)
        return

    # Run tests
    test_mission_list_and_scoping()
    test_rf_request_create_rbac(sat_id, mission_id)
    test_request_list_scoping()
    test_excone_create_rbac(sat_id, gs_id)
    test_excone_list_basic()
    test_users_list_rbac()
    test_scheduler_basic(sat_id, mission_id)


 # Extra: basic visibility for other subsystems
    test_satellites_basic_visibility()
    test_ground_stations_basic_visibility()
    
if __name__ == "__main__":
    main()
