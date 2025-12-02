# test_schedule_router.py

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.routers import schedule as schedule_router
from app.services.db import get_db


# ---------------------------
# 1. Dummy SchedulerService
# ---------------------------

class DummyScheduler:
    """
    Lightweight stub that mimics the real SchedulerService interface,
    so we don't hit Skyfield, SQL, etc. in route tests.
    """
    def __init__(self, db):
        self.db = db

    def replan(self, mission_id=None):
        return {
            "run_id": "test-run-123",
            "scheduled": [
                {
                    "request_id": "00000000-0000-0000-0000-000000000001",
                    "request_type": "RF",
                    "mission": "TEST_MISSION",
                    "satellite": "TEST_SAT_1",
                    "groundStation": "TEST_GS_1",
                    "groundStationId": 1,
                    "aos": "2025-01-01T00:00:00Z",
                    "rf_on": "2025-01-01T00:01:00Z",
                    "rf_off": "2025-01-01T00:09:00Z",
                    "los": "2025-01-01T00:10:00Z",
                    "duration": 600.0,
                    "priority": 3,
                }
            ],
            "deferred": [],
            "conflicts": [],
            "metrics": {
                "numRequests": 1,
                "numScheduled": 1,
                "numDeferred": 0,
                "fulfillmentRate": 1.0,
            },
        }

    def whatif(self, request_id: int):
        return {
            "status": "scheduled",
            "request_id": request_id,
            "dry_run": True,
            "contact": {
                "mission": "TEST_MISSION",
                "satellite": "TEST_SAT_1",
                "station": "TEST_GS_1",
                "aos": "2025-01-01T01:00:00Z",
                "rf_on": "2025-01-01T01:01:00Z",
                "rf_off": "2025-01-01T01:09:00Z",
                "los": "2025-01-01T01:10:00Z",
            },
        }


# ---------------------------
# 2. Test app wiring
# ---------------------------

def override_get_db():
    """
    DB dependency override for tests.
    Router only passes this into DummyScheduler; we don't actually use it.
    """
    yield None


# Monkeypatch the scheduler used *inside the router module*
schedule_router.SchedulerService = DummyScheduler  # type: ignore[attr-defined]

# Build a tiny FastAPI app specifically for these tests
app = FastAPI()
app.dependency_overrides[get_db] = override_get_db
app.include_router(schedule_router.router)

client = TestClient(app)

# Use the real router prefix so we don't guess paths
BASE = schedule_router.router.prefix or ""   # e.g. "/api/v1/schedule"


# ---------------------------
# 3. Tests
# ---------------------------

def test_replan_route_basic():
    # Route path = <router.prefix> + "/replan"
    url = f"{BASE}/replan"
    resp = client.post(url, params={"mission_id": 1})
    assert resp.status_code == 200

    data = resp.json()

    # Basic shape
    assert "run_id" in data
    assert "scheduled" in data
    assert "deferred" in data
    assert "metrics" in data

    # From our DummyScheduler
    assert data["run_id"] == "test-run-123"
    assert data["metrics"]["numRequests"] == 1
    assert len(data["scheduled"]) == 1

    first = data["scheduled"][0]
    assert first["mission"] == "TEST_MISSION"
    assert first["satellite"] == "TEST_SAT_1"
    assert first["groundStationId"] == 1
    assert first["request_type"] == "RF"


def test_whatif_route_basic():
    url = f"{BASE}/whatif"
    resp = client.post(url, params={"request_id": 42})
    assert resp.status_code == 200

    data = resp.json()

    assert data["status"] == "scheduled"
    assert data["request_id"] == 42
    assert data["dry_run"] is True
    assert "contact" in data

    contact = data["contact"]
    assert contact["mission"] == "TEST_MISSION"
    assert contact["satellite"] == "TEST_SAT_1"
    assert contact["station"] == "TEST_GS_1"
