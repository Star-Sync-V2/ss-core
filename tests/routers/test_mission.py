# tests/routers/test_mission.py

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services.auth import get_current_user


# --- simple dummy user object for tests ---
class DummyUser:
    def __init__(self, role: str, mission_id: int | None = None):
        self.role = role
        self.mission_id = mission_id


def override_user_with_role(role: str, mission_id: int | None = None):
    def _override():
        return DummyUser(role=role, mission_id=mission_id)
    return _override


@pytest.fixture
def client():
    return TestClient(app)


def test_system_admin_can_create_and_list_missions(client):
    # system_admin creates a mission
    app.dependency_overrides[get_current_user] = override_user_with_role("system_admin")

    create_resp = client.post(
        "/api/v1/mission",
        json={"name": "SCISAT", "description": "SCISAT mission"},
    )
    assert create_resp.status_code in (200, 201)
    created = create_resp.json()
    assert created["name"] == "SCISAT"
    mission_id = created["id"]

    # system_admin can list missions
    list_resp = client.get("/api/v1/mission")
    assert list_resp.status_code == 200
    missions = list_resp.json()
    assert any(m["id"] == mission_id for m in missions)

    app.dependency_overrides.clear()


def test_mission_admin_cannot_create_mission(client):
    app.dependency_overrides[get_current_user] = override_user_with_role(
        "mission_admin", mission_id=1
    )

    resp = client.post(
        "/api/v1/mission",
        json={"name": "NOPE", "description": "Should not be allowed"},
    )
    assert resp.status_code == 403

    app.dependency_overrides.clear()


def test_system_user_cannot_create_mission(client):
    app.dependency_overrides[get_current_user] = override_user_with_role("system_user")

    resp = client.post(
        "/api/v1/mission",
        json={"name": "NOPE2", "description": "Should not be allowed"},
    )
    assert resp.status_code == 403

    app.dependency_overrides.clear()


def test_any_role_can_list_missions(client):
    # ensure at least one mission exists
    app.dependency_overrides[get_current_user] = override_user_with_role("system_admin")
    client.post(
        "/api/v1/mission",
        json={"name": "LISTABLE", "description": "For list tests"},
    )

    # All roles should be able to list missions (for now)
    for role in ["system_admin", "system_user", "mission_admin", "mission_user"]:
        app.dependency_overrides[get_current_user] = override_user_with_role(
            role, mission_id=1
        )
        resp = client.get("/api/v1/mission")
        assert resp.status_code == 200
        missions = resp.json()
        assert isinstance(missions, list)

    app.dependency_overrides.clear()


def test_system_admin_can_update_and_delete_mission(client):
    # create mission as system_admin
    app.dependency_overrides[get_current_user] = override_user_with_role("system_admin")
    create_resp = client.post(
        "/api/v1/mission",
        json={"name": "TEMP", "description": "To be updated/deleted"},
    )
    assert create_resp.status_code in (200, 201)
    mission_id = create_resp.json()["id"]

    # update as system_admin
    update_resp = client.patch(
        f"/api/v1/mission/{mission_id}",
        json={"description": "Updated"},
    )
    assert update_resp.status_code == 200
    assert update_resp.json()["description"] == "Updated"

    # delete as system_admin
    delete_resp = client.delete(f"/api/v1/mission/{mission_id}")
    assert delete_resp.status_code in (200, 204)

    app.dependency_overrides.clear()


def test_other_roles_cannot_update_or_delete_mission(client):
    # create mission as sysadmin
    app.dependency_overrides[get_current_user] = override_user_with_role("system_admin")
    create_resp = client.post(
        "/api/v1/mission",
        json={"name": "LOCKED", "description": "Protected"},
    )
    assert create_resp.status_code in (200, 201)
    mission_id = create_resp.json()["id"]

    # roles that should NOT be able to update/delete
    for role in ["system_user", "mission_admin", "mission_user"]:
        app.dependency_overrides[get_current_user] = override_user_with_role(role, 1)

        update_resp = client.patch(
            f"/api/v1/mission/{mission_id}",
            json={"description": "Hack"},
        )
        assert update_resp.status_code == 403

        delete_resp = client.delete(f"/api/v1/mission/{mission_id}")
        assert delete_resp.status_code == 403

    app.dependency_overrides.clear()
