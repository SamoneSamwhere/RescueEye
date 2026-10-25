"""
Tests for the drone-agnostic telemetry layer.

The contract these pin down is what lets any aircraft drive the platform:
a real fix outranks the simulation, a stale one does not, and losing the link
degrades to a labelled simulated track rather than freezing the last position.
"""
import time

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from auth_helpers import AUTH_HEADERS

from routers import drone as drone_router
from services import drone_telemetry, telemetry_sources
from services.telemetry_sources import TelemetryFix


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    telemetry_sources.reset_for_tests()
    monkeypatch.setenv("TELEMETRY_SOURCE", "auto")
    yield
    telemetry_sources.reset_for_tests()


@pytest.fixture()
def client():
    app = FastAPI()
    app.include_router(drone_router.router, prefix="/drone")
    return TestClient(app, headers=AUTH_HEADERS)


def _fix(**kw):
    base = dict(lat=10.3, lng=123.89, received_at=time.monotonic(), source="push")
    base.update(kw)
    return TelemetryFix(**base)


# ── Source selection ──────────────────────────────────────────────────────────

def test_no_real_source_means_simulated():
    assert telemetry_sources.live_fix() is None
    assert drone_telemetry.is_simulated() is True
    assert drone_telemetry.current_state().source == "simulated"


def test_a_pushed_fix_outranks_the_simulation():
    telemetry_sources.push_source().submit(_fix(lat=10.321, lng=123.901))
    state = drone_telemetry.current_state()
    assert state.source == "push"
    assert (round(state.lat, 3), round(state.lng, 3)) == (10.321, 123.901)
    assert drone_telemetry.is_simulated() is False


def test_a_stale_fix_is_ignored_and_the_simulation_resumes():
    """A dropped link must not pin every later detection to the last position."""
    old = time.monotonic() - (telemetry_sources.STALE_AFTER_S + 1)
    telemetry_sources.push_source().submit(_fix(received_at=old))
    assert telemetry_sources.live_fix() is None
    assert drone_telemetry.current_state().source == "simulated"


def test_simulated_mode_ignores_real_fixes(monkeypatch):
    monkeypatch.setenv("TELEMETRY_SOURCE", "simulated")
    telemetry_sources.push_source().submit(_fix())
    assert telemetry_sources.live_fix() is None


def test_fixes_are_tracked_per_drone():
    telemetry_sources.push_source().submit(_fix(drone_id="DRN-01", lat=10.30))
    telemetry_sources.push_source().submit(_fix(drone_id="DRN-02", lat=10.34))
    assert round(telemetry_sources.live_fix("DRN-01").lat, 2) == 10.30
    assert round(telemetry_sources.live_fix("DRN-02").lat, 2) == 10.34
    assert telemetry_sources.push_source().known_drones() == ["DRN-01", "DRN-02"]


def test_unknown_drone_id_has_no_fix():
    telemetry_sources.push_source().submit(_fix(drone_id="DRN-01"))
    assert telemetry_sources.live_fix("DRN-99") is None


def test_optional_fields_survive_the_round_trip():
    telemetry_sources.push_source().submit(_fix(altitude_m=62.5, heading_deg=270.0, speed_mps=8.0))
    state = drone_telemetry.current_state()
    assert state.altitude_m == 62.5
    assert round(state.heading_deg) == 270
    assert state.speed_mps == 8.0


# ── HTTP surface ──────────────────────────────────────────────────────────────

def test_push_endpoint_accepts_a_minimal_fix(client):
    """lat/lng only — demanding more would lock out simpler platforms."""
    r = client.post("/drone/telemetry", json={"lat": 10.31, "lng": 123.9})
    assert r.status_code == 202
    assert client.get("/drone/telemetry").json()["source"] == "push"


def test_push_endpoint_rejects_impossible_coordinates(client):
    assert client.post("/drone/telemetry", json={"lat": 99.0, "lng": 123.9}).status_code == 422
    assert client.post("/drone/telemetry", json={"lat": 10.3, "lng": 999.0}).status_code == 422
    assert client.post("/drone/telemetry", json={"lat": 10.3}).status_code == 422


def test_telemetry_reports_simulated_honestly(client):
    before = client.get("/drone/telemetry").json()
    assert before["simulated"] is True and before["source"] == "simulated"

    client.post("/drone/telemetry", json={"lat": 10.31, "lng": 123.9, "altitudeM": 55})
    after = client.get("/drone/telemetry").json()
    assert after["simulated"] is False
    assert after["source"] == "push"
    assert after["altitudeM"] == 55.0


def test_sources_endpoint_describes_what_is_available(client):
    body = client.get("/drone/sources").json()
    assert body["simulated"] is True
    assert body["sources"]["push"]["available"] is True
    assert body["sources"]["mavlink"]["available"] is False   # no MAVLINK_CONNECTION
    client.post("/drone/telemetry", json={"lat": 10.31, "lng": 123.9, "droneId": "DRN-07"})
    assert "DRN-07" in client.get("/drone/sources").json()["sources"]["push"]["dronesReporting"]


# ── MAVLink wiring ────────────────────────────────────────────────────────────

def test_mavlink_is_not_started_without_a_connection_string(monkeypatch):
    monkeypatch.delenv("MAVLINK_CONNECTION", raising=False)
    telemetry_sources.configure("auto")
    assert telemetry_sources.mavlink_source() is None


def test_mavlink_source_is_created_when_configured(monkeypatch):
    monkeypatch.setenv("MAVLINK_CONNECTION", "udp:127.0.0.1:14550")
    # Never actually dial out during a unit test.
    monkeypatch.setattr(telemetry_sources.MavlinkSource, "start", lambda self: None)
    telemetry_sources.configure("auto")
    source = telemetry_sources.mavlink_source()
    assert source is not None
    assert source.connection == "udp:127.0.0.1:14550"


def test_mavlink_fix_is_used_when_fresh(monkeypatch):
    monkeypatch.setenv("MAVLINK_CONNECTION", "udp:127.0.0.1:14550")
    monkeypatch.setattr(telemetry_sources.MavlinkSource, "start", lambda self: None)
    telemetry_sources.configure("auto")
    telemetry_sources.mavlink_source()._fix = _fix(source="mavlink", lat=10.333, altitude_m=80.0)
    state = drone_telemetry.current_state()
    assert state.source == "mavlink"
    assert state.altitude_m == 80.0


def test_push_wins_when_both_sources_are_live(monkeypatch):
    """Push is the explicitly bridged path, so it takes precedence on a tie."""
    monkeypatch.setenv("MAVLINK_CONNECTION", "udp:127.0.0.1:14550")
    monkeypatch.setattr(telemetry_sources.MavlinkSource, "start", lambda self: None)
    telemetry_sources.configure("auto")
    now = time.monotonic()
    telemetry_sources.mavlink_source()._fix = _fix(source="mavlink", lat=10.111, received_at=now)
    telemetry_sources.push_source().submit(_fix(source="push", lat=10.222, received_at=now))
    assert telemetry_sources.live_fix().source == "push"
