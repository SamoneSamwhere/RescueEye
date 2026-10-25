"""
Tests for the responder position registry and its endpoint.

The point of this feature is that the system should never report its own
rescue team as casualties. It cannot see the difference — a rescuer is a
person like any other — so it uses the positions the console already reports.
"""
import time

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from auth_helpers import AUTH_HEADERS

from routers import responders
from services import responder_registry


@pytest.fixture(autouse=True)
def _clean_registry():
    """Positions are module-level state; without this, tests leak into each other."""
    responder_registry.reset()
    yield
    responder_registry.reset()


@pytest.fixture()
def client():
    responder_registry.reset()
    app = FastAPI()
    app.include_router(responders.router, prefix="/responders")
    yield TestClient(app, headers=AUTH_HEADERS)
    responder_registry.reset()


# ── Distance ──────────────────────────────────────────────────────────────────

def test_haversine_matches_a_known_separation():
    # One degree of latitude is ~111km anywhere on the globe.
    d = responder_registry.haversine_m(10.0, 123.0, 11.0, 123.0)
    assert d == pytest.approx(111_195, rel=0.01)


def test_nearest_picks_the_closest_of_several():
    responder_registry.report("far", 10.4000, 123.8854)
    responder_registry.report("near", 10.3158, 123.8854)
    pos, dist = responder_registry.nearest(10.3157, 123.8854)
    assert pos.responder_id == "near"
    assert dist < 30


def test_no_position_means_no_match():
    matched, who = responder_registry.is_known_responder(None, None)
    assert matched is False
    assert who == ""


# ── Exclusion ─────────────────────────────────────────────────────────────────

def test_point_on_a_responder_matches():
    responder_registry.report("u1", 10.3157, 123.8854, name="Casey Nolan")
    matched, who = responder_registry.is_known_responder(10.3157, 123.8854)
    assert matched is True
    assert who == "Casey Nolan"


def test_point_beyond_the_radius_does_not_match():
    responder_registry.report("u1", 10.3157, 123.8854)
    matched, _ = responder_registry.is_known_responder(10.3157, 123.8854, radius_m=1.0)
    # Same point is still within 1m of itself, so move it ~110m north.
    matched_far, _ = responder_registry.is_known_responder(10.3167, 123.8854, radius_m=15.0)
    assert matched is True
    assert matched_far is False


def test_stale_positions_expire(monkeypatch):
    """
    A fix from ten minutes ago would otherwise keep vetoing casualties at a
    spot the responder has long since left — worse than having no fix at all.
    """
    monkeypatch.setattr(responder_registry, "RESPONDER_TTL_S", 0.05)
    responder_registry.report("u1", 10.3157, 123.8854)
    assert len(responder_registry.active()) == 1
    time.sleep(0.08)
    assert responder_registry.active() == []
    matched, _ = responder_registry.is_known_responder(10.3157, 123.8854)
    assert matched is False


# ── Endpoint ──────────────────────────────────────────────────────────────────

def test_post_positions_accepts_a_batch(client):
    res = client.post("/responders/positions", json={"responders": [
        {"id": "u1", "lat": 10.3157, "lng": 123.8854, "name": "Casey"},
        {"id": "u2", "lat": 10.3160, "lng": 123.8860, "name": "Diego"},
    ]})
    assert res.status_code == 200
    assert res.json() == {"accepted": 2, "active": 2}


def test_malformed_entries_do_not_reject_the_batch(client):
    """One bad row must not cost the good rows in the same report."""
    res = client.post("/responders/positions", json={"responders": [
        {"id": "u1", "lat": 10.3157, "lng": 123.8854},
        {"id": "", "lat": 1, "lng": 2},
        {"id": "u3", "lat": "not-a-number", "lng": 2},
        {"id": "u4", "lng": 2},
        "garbage",
    ]})
    assert res.status_code == 200
    assert res.json()["accepted"] == 1


def test_missing_list_is_rejected(client):
    assert client.post("/responders/positions", json={}).status_code == 422


def test_list_reports_active_positions(client):
    client.post("/responders/positions", json={"responders": [
        {"id": "u1", "lat": 10.3157, "lng": 123.8854, "name": "Casey"},
    ]})
    body = client.get("/responders").json()
    assert [r["id"] for r in body["responders"]] == ["u1"]
    assert body["exclusion_radius_m"] == responder_registry.RESPONDER_EXCLUSION_M


def test_delete_clears_positions(client):
    client.post("/responders/positions", json={"responders": [
        {"id": "u1", "lat": 10.3157, "lng": 123.8854},
    ]})
    assert client.delete("/responders").json() == {"cleared": True}
    assert client.get("/responders").json()["responders"] == []
