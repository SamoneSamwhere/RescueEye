"""POST /detections/demo: a rehearsal casualty placed near a responder."""
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from routers import detections
from services import auth, detection_store, responder_registry


@pytest.fixture()
def client():
    detection_store._store.clear()
    responder_registry.reset()
    app = FastAPI()
    app.include_router(detections.router, prefix="/detections")
    yield TestClient(app)
    detection_store._store.clear()
    responder_registry.reset()


def _headers(role="COMMAND_STAFF", agency="7"):
    return {"Authorization": f"Bearer {auth.issue_token('1', role, agency)}"}


def test_demo_casualty_lands_near_the_responder_but_outside_the_veto(client):
    responder_registry.report("29", 10.2931187, 123.9012631, name="Danniezon", agency_id="7")
    res = client.post("/detections/demo", headers=_headers())
    assert res.status_code == 200
    body = res.json()
    distance = responder_registry.haversine_m(10.2931187, 123.9012631, body["lat"], body["lng"])
    assert responder_registry.RESPONDER_EXCLUSION_M < distance < 100
    assert body["nearResponder"]["name"] == "Danniezon"

    stored = client.get("/detections/recent").json()["detections"][0]
    assert stored["id"] == body["id"] and stored["class"] == "casualty"
    assert stored["confidence"] >= 0.75             # enough to pop up
    assert stored["location_source"] == "simulated"


def test_demo_casualty_ignores_other_agencies_responders(client):
    responder_registry.report("29", 10.29, 123.90, name="Elsewhere", agency_id="8")
    assert client.post("/detections/demo", headers=_headers(agency="7")).status_code == 404


def test_demo_casualty_at_an_exact_point(client):
    res = client.post("/detections/demo", headers=_headers(), json={"lat": 10.3, "lng": 123.9})
    assert res.status_code == 200 and (res.json()["lat"], res.json()["lng"]) == (10.3, 123.9)


def test_field_responders_cannot_create_one(client):
    res = client.post("/detections/demo", headers=_headers(role="FIELD_RESPONDER"), json={"lat": 10.3, "lng": 123.9})
    assert res.status_code == 403
