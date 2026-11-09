"""Organizations working the same area, and who leads (services/operations_registry.py)."""
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from routers import operations
from services import auth, operations_registry as ops

UC_BANILAD = {"lat": 10.3385, "lng": 123.9118}


@pytest.fixture()
def client(monkeypatch):
    ops.reset()
    monkeypatch.setenv("DEMO_MODE", "true")
    app = FastAPI()
    app.include_router(operations.router, prefix="/operations")
    yield TestClient(app)
    ops.reset()


def h(agency, role="COMMAND_STAFF"):
    return {"Authorization": f"Bearer {auth.issue_token('1', role, agency)}"}


def share(client, agency, name, verified, at=UC_BANILAD, responders=()):
    return client.put("/operations/mine", headers=h(agency), json={
        "agencyName": name,
        "incidents": [{"id": "i1", **at, "verifiedAt": verified}],
        "responders": [{"lat": r[0], "lng": r[1], "busy": True, "name": "Juan", "phone": "0917"} for r in responders],
    })


def test_first_to_verify_leads_and_the_lead_passes_on(client):
    share(client, "7", "Mandaue SAR", "2026-11-09T08:00:00+00:00")
    share(client, "8", "Cebu Rescue", "2026-11-09T07:00:00+00:00", at={"lat": 10.3400, "lng": 123.9130})
    view = client.get("/operations/nearby", headers=h("7")).json()
    assert view["leadAgencyId"] == "8"
    assert {a["agencyId"]: a["isLead"] for a in view["agencies"]} == {"7": False, "8": True}

    client.delete("/operations/mine", headers=h("8"))          # agency 8 finished
    assert client.get("/operations/nearby", headers=h("7")).json()["leadAgencyId"] == "7"


def test_far_away_agencies_are_not_shown(client):
    share(client, "7", "Mandaue SAR", "2026-11-09T08:00:00+00:00")
    share(client, "9", "Davao Rescue", "2026-11-09T06:00:00+00:00", at={"lat": 7.0731, "lng": 125.6128})
    view = client.get("/operations/nearby", headers=h("7")).json()
    assert [a["agencyId"] for a in view["agencies"]] == ["7"]


def test_no_names_or_phones_are_kept(client):
    share(client, "7", "Mandaue SAR", "2026-11-09T08:00:00+00:00", responders=[(10.3386, 123.9119)])
    share(client, "8", "Cebu Rescue", "2026-11-09T09:00:00+00:00")
    other = [a for a in client.get("/operations/nearby", headers=h("8")).json()["agencies"] if a["agencyId"] == "7"][0]
    assert other["responders"] == [{"lat": 10.3386, "lng": 123.9119, "busy": True}]


def test_nothing_to_show_without_an_open_incident(client):
    share(client, "8", "Cebu Rescue", "2026-11-09T09:00:00+00:00")
    client.put("/operations/mine", headers=h("7"), json={"agencyName": "Mandaue SAR", "incidents": [], "responders": []})
    assert client.get("/operations/nearby", headers=h("7")).json()["agencies"] == []


def test_demo_agency_leads_then_ends(client):
    share(client, "7", "Mandaue SAR", "2026-11-09T08:00:00+00:00")
    view = client.post("/operations/demo", headers=h("7"), json={**UC_BANILAD, "lead": True}).json()
    assert view["leadAgencyId"] == ops.demo_agency_id("7") and len(view["agencies"]) == 2
    share(client, "8", "Cebu Rescue", "2026-11-09T09:00:00+00:00")
    seen_by_8 = [a["agencyId"] for a in client.get("/operations/nearby", headers=h("8")).json()["agencies"]]
    assert ops.demo_agency_id("7") not in seen_by_8
    view = client.delete("/operations/demo", headers=h("7")).json()
    assert view["leadAgencyId"] == "7"


def test_field_responders_cannot_see_or_place(client, monkeypatch):
    monkeypatch.setenv("DEMO_MODE", "false")
    assert client.get("/operations/nearby", headers=h("7", "FIELD_RESPONDER")).status_code == 403
    assert client.post("/operations/demo", headers=h("7", "FIELD_RESPONDER"), json=UC_BANILAD).status_code == 403
    assert client.post("/operations/demo", headers=h("7"), json=UC_BANILAD).status_code == 200
