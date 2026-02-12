
"""
Advanced Scheduler Smoke + Edge Tests

Run:
    cd ss-core
    source .venv/bin/activate
    python schedule_smoke.py

Prereqs:
    Backend running at http://localhost:8000
    /api/v1/hello/initdb
    /api/v1/hello/create_demo_data
"""

import requests
import sys
from datetime import datetime, timedelta

BASE_URL = "http://localhost:8000/api/v1"
TIMEOUT = 10
MIN_GAP_SECONDS = 300

ROLES = {
    "system_admin": ("system_admin", "system_admin"),
    "system_user": ("system_user", "system_user"),
    "mission_admin": ("mission_admin", "mission_admin"),
    "mission_user": ("mission_user", "mission_user"),
}

TOKENS = {}


# -------------------------------------------------------
# Utilities
# -------------------------------------------------------

def fail(msg):
    print(f"[FAIL] {msg}")
    sys.exit(1)


def ok(msg):
    print(f"[PASS] {msg}")


def parse_iso(dt_str: str) -> datetime:
    if dt_str.endswith("Z"):
        dt_str = dt_str[:-1] + "+00:00"
    return datetime.fromisoformat(dt_str)


def gap_ok(a_start, a_end, b_start, b_end):
    gap = timedelta(seconds=MIN_GAP_SECONDS)
    return (a_end + gap <= b_start) or (b_end + gap <= a_start)


def call(method, path, role, json_body=None):
    headers = {
        "Authorization": f"Bearer {TOKENS[role]}",
        "Content-Type": "application/json",
    }
    return requests.request(
        method,
        BASE_URL + path,
        headers=headers,
        json=json_body,
        timeout=TIMEOUT,
    )


# -------------------------------------------------------
# Auth bootstrap
# -------------------------------------------------------

def fetch_tokens():
    for role, creds in ROLES.items():
        resp = requests.post(
            BASE_URL + "/auth/token",
            data={
                "grant_type": "password",
                "username": creds[0],
                "password": creds[1],
            },
            timeout=TIMEOUT,
        )
        if resp.status_code != 200:
            fail(f"Token fetch failed for {role}")
        TOKENS[role] = resp.json()["access_token"]
    ok("Tokens fetched")


# -------------------------------------------------------
# Bootstrap data
# -------------------------------------------------------

def bootstrap():
    r_sat = call("GET", "/satellites/", "system_admin")
    r_gs = call("GET", "/gs/", "system_admin")

    sats = r_sat.json()
    gss = r_gs.json()

    if not sats or not gss:
        fail("No satellites or ground stations found")

    main_sat = sats[0]
    mission_id = main_sat.get("mission_id", 1)
    gs_id = gss[0]["id"]

    return main_sat, mission_id, gs_id


# -------------------------------------------------------
# RF helpers
# -------------------------------------------------------

def create_rf(sat_id, mission_id, start, end):
    body = {
        "missionName": "SMOKE_TEST",
        "mission_id": mission_id,
        "satelliteId": sat_id,
        "startTime": start,
        "endTime": end,
        "uplinkTime": 600,
        "downlinkTime": 600,
        "scienceTime": 300,
        "minimumNumberOfPasses": 1,
    }
    r = call("POST", "/request/rf-time", "system_admin", body)
    if r.status_code != 200:
        fail("RF creation failed")
    return r.json()["id"]


def delete_rf(req_id):
    call("DELETE", f"/request/rf-time/{req_id}", "system_admin")


# -------------------------------------------------------
# Scheduler call
# -------------------------------------------------------

def compute(window_start, window_end, mission_id, role="system_admin"):
    body = {
        "windowStart": window_start,
        "windowEnd": window_end,
        "missionId": mission_id,
    }
    r = call("POST", "/schedule/compute", role, body)
    if r.status_code != 200:
        fail(f"Scheduler failed ({role})")
    return r.json()


# -------------------------------------------------------
# Core invariant checks
# -------------------------------------------------------

def validate_schedule_response(resp, window_start, window_end):
    if "schedule" not in resp or "metrics" not in resp:
        fail("Missing schedule or metrics in response")

    schedule = resp["schedule"]

    ws = parse_iso(window_start)
    we = parse_iso(window_end)

    for c in schedule:
        aos = parse_iso(c["aos"])
        los = parse_iso(c["los"])

        if not aos < los:
            fail("Invalid interval: aos >= los")

        if not (aos < we and los > ws):
            fail("Contact outside scheduling window")

    ok("Schedule structure valid")


def validate_resource_constraints(schedule):
    by_station = {}
    by_sat = {}

    for c in schedule:
        by_station.setdefault(c["groundStationId"], []).append(c)
        by_sat.setdefault(c["satelliteId"], []).append(c)

    for entries in by_station.values():
        entries = sorted(entries, key=lambda x: parse_iso(x["aos"]))
        for i in range(len(entries) - 1):
            a = entries[i]
            b = entries[i + 1]
            if not gap_ok(
                parse_iso(a["aos"]),
                parse_iso(a["los"]),
                parse_iso(b["aos"]),
                parse_iso(b["los"]),
            ):
                fail("Station guard-band violation")

    for entries in by_sat.values():
        entries = sorted(entries, key=lambda x: parse_iso(x["aos"]))
        for i in range(len(entries) - 1):
            a = entries[i]
            b = entries[i + 1]
            if not gap_ok(
                parse_iso(a["aos"]),
                parse_iso(a["los"]),
                parse_iso(b["aos"]),
                parse_iso(b["los"]),
            ):
                fail("Satellite guard-band violation")

    ok("Resource constraints valid")


# -------------------------------------------------------
# Tests
# -------------------------------------------------------

def test_basic_overlap(main_sat, mission_id):
    ws = "2025-12-02T00:00:00Z"
    we = "2025-12-02T06:00:00Z"

    r1 = create_rf(main_sat["id"], mission_id,
                   "2025-12-02T01:00:00Z",
                   "2025-12-02T04:00:00Z")
    r2 = create_rf(main_sat["id"], mission_id,
                   "2025-12-02T02:00:00Z",
                   "2025-12-02T05:00:00Z")

    try:
        resp = compute(ws, we, mission_id)
        validate_schedule_response(resp, ws, we)
        validate_resource_constraints(resp["schedule"])
    finally:
        delete_rf(r1)
        delete_rf(r2)


def test_no_candidates(main_sat, mission_id):
    ws = "2035-01-01T00:00:00Z"
    we = "2035-01-01T01:00:00Z"

    resp = compute(ws, we, mission_id)
    if resp["schedule"]:
        fail("Expected empty schedule for future window")

    ok("No candidate scenario handled")


def test_mission_isolation(main_sat, mission_id):
    ws = "2025-12-02T00:00:00Z"
    we = "2025-12-02T06:00:00Z"

    resp = compute(ws, we, mission_id)

    for c in resp["schedule"]:
        if c.get("missionId") != mission_id:
            fail("Mission leakage detected")

    ok("Mission isolation verified")


def test_rbac_compute(mission_id):
    ws = "2025-12-02T00:00:00Z"
    we = "2025-12-02T06:00:00Z"

    # system_user should at least not crash
    compute(ws, we, mission_id, role="system_user")
    ok("RBAC compute allowed for system_user")


# -------------------------------------------------------
# Main
# -------------------------------------------------------

def main():
    fetch_tokens()
    main_sat, mission_id, _ = bootstrap()

    test_basic_overlap(main_sat, mission_id)
    test_no_candidates(main_sat, mission_id)
    test_mission_isolation(main_sat, mission_id)
    test_rbac_compute(mission_id)

    print("\nALL TESTS PASSED")


if __name__ == "__main__":
    main()