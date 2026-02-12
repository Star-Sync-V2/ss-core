# FIX: Your backend metrics keys don't match expected names.
# This version auto-detects metric aliases and validates correctly.
# Replace your determinism_test.py metrics section with this FULL file.

import requests
import json
import hashlib
import sys

BASE_URL = "http://localhost:8000/api/v1"
TIMEOUT = 10
TOKEN = None




def fail(msg):
    print(f"[FAIL] {msg}")
    sys.exit(1)


def ok(msg):
    print(f"[PASS] {msg}")


def fetch_token():
    global TOKEN
    r = requests.post(
        BASE_URL + "/auth/token",
        data={
            "grant_type": "password",
            "username": "system_admin",
            "password": "system_admin",
        },
        timeout=TIMEOUT,
    )
    if r.status_code != 200:
        fail("Token fetch failed")
    TOKEN = r.json()["access_token"]


def call_schedule():
    headers = {
        "Authorization": f"Bearer {TOKEN}",
        "Content-Type": "application/json",
    }

    body = {
        "windowStart": "2025-12-02T00:00:00Z",
        "windowEnd": "2025-12-02T06:00:00Z",
        "missionId": 1,
    }

    r = requests.post(
        BASE_URL + "/schedule/compute",
        headers=headers,
        json=body,
        timeout=TIMEOUT,
    )

    if r.status_code != 200:
        fail("Scheduler compute failed")

    return r.json()


def normalize_schedule(resp):
    schedule = resp.get("schedule", [])

    normalized = sorted(
        [
            {
                "sat": c["satelliteId"],
                "gs": c["groundStationId"],
                "aos": c["aos"],
                "los": c["los"],
            }
            for c in schedule
        ],
        key=lambda x: (x["sat"], x["gs"], x["aos"]),
    )

    return normalized


def hash_obj(obj):
    return hashlib.sha256(json.dumps(obj, sort_keys=True).encode()).hexdigest()


# ---------------- METRIC FIX ----------------

METRIC_ALIASES = {
    "scheduled_count": ["scheduled_count", "scheduledContacts", "scheduled"],
    "requests_count": ["requests_count", "totalRequests", "requests"],
    "deferred_count": ["deferred_count", "deferredContacts", "deferred"],
}


def resolve_metric(metrics, key):
    for alias in METRIC_ALIASES[key]:
        if alias in metrics:
            return metrics[alias]
    fail(f"Missing metric group: {key}")


def test_metrics_consistency():
    resp = call_schedule()
    metrics = resp.get("metrics", {})

    scheduled = resolve_metric(metrics, "scheduled_count")
    requests = resolve_metric(metrics, "requests_count")
    deferred = resolve_metric(metrics, "deferred_count")

    if scheduled > requests:
        fail("scheduled > requests")

    if scheduled + deferred < requests:
        fail("scheduled + deferred < requests (missing accounting)")

    ok("Metrics consistency verified")


# ---------------- DETERMINISM ----------------

def test_determinism():
    resp1 = call_schedule()
    resp2 = call_schedule()

    h1 = hash_obj(normalize_schedule(resp1))
    h2 = hash_obj(normalize_schedule(resp2))

    if h1 != h2:
        fail("Scheduler is NOT deterministic")

    ok("Deterministic scheduling verified")


def test_repeat_load(iterations=10):
    baseline = hash_obj(normalize_schedule(call_schedule()))

    for i in range(iterations):
        current = hash_obj(normalize_schedule(call_schedule()))
        if current != baseline:
            fail(f"Schedule changed during repeated calls (iteration {i})")

    ok(f"Scheduler stable across {iterations} repeated calls")


def main():
    fetch_token()
    test_determinism()
    test_metrics_consistency()
    test_repeat_load()
    print("\nDETERMINISM SUITE PASSED")


if __name__ == "__main__":
    main()