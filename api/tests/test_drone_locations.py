"""
Drone positions (services/drone_locations.py, GET /drone/positions).

What must hold: the drone's own GPS beats the pilot's phone; a pilot position
carries the wide accuracy it deserves; a fix belongs only to the drone it was
reported for; nothing is invented outside demo mode; and a streaming drone
with no position is listed as unknown, not placed somewhere.
"""
import time

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from auth_helpers import AUTH_HEADERS
from routers import drone, responders
from services import drone_locations, feed_registry, telemetry_sources
from services.telemetry_sources import TelemetryFix


@pytest.fixture(autouse=True)
def clean(monkeypatch):
    monkeypatch.setenv("DEMO_MODE", "false")
    monkeypatch.setattr(feed_registry, "_start_producer", lambda feed: None)
    telemetry_sources.reset_for_tests()
    drone_locations.reset()
    feed_registry.shutdown_all()
    yield
    telemetry_sources.reset_for_tests()
    drone_locations.reset()
    feed_registry.shutdown_all()


def gps(drone_id, lat=10.30, lng=123.90, **extra):
    telemetry_sources.push_source().submit(TelemetryFix(
        lat=lat, lng=lng, received_at=time.monotonic(), source="push", drone_id=drone_id,
        altitude_m=40.0, extra=extra,
    ))


def test_drone_gps_is_used_with_the_accuracy_the_bridge_reports():
    gps("alpha", accuracy_m=2.5, method="sdk")
    loc = drone_locations.locate("alpha")
    assert (loc.source, loc.method, loc.accuracy_m) == ("drone_gps", "sdk", 2.5)
    assert loc.can_georeference


def test_drone_gps_without_a_reported_accuracy_gets_a_per_method_default():
    gps("alpha", method="remote_id")
    assert drone_locations.locate("alpha").accuracy_m == drone_locations.DEFAULT_ACCURACY_M["remote_id"]


def test_pilot_phone_is_a_wide_circle_and_cannot_place_subjects():
    drone_locations.report_pilot("alpha", 10.31, 123.91, 12.0, "28", "Sam", "13")
    loc = drone_locations.locate("alpha")
    assert loc.source == "pilot"
    assert loc.accuracy_m == 12.0 + drone_locations.PILOT_STANDOFF_M
    assert not loc.can_georeference
    assert loc.pilot_name == "Sam"


def test_drone_gps_beats_the_pilot_phone():
    drone_locations.report_pilot("alpha", 10.31, 123.91, 12.0, "28", "Sam", "13")
    gps("alpha", lat=10.40)
    assert drone_locations.locate("alpha").lat == 10.40


def test_one_drones_fix_is_not_used_for_another():
    gps("alpha")
    assert drone_locations.locate("bravo") is None


def test_nothing_is_invented_outside_demo_mode(monkeypatch):
    assert drone_locations.locate("alpha") is None
    monkeypatch.setenv("DEMO_MODE", "true")
    assert drone_locations.locate("alpha").source == "simulated"


def test_a_stale_pilot_position_is_dropped(monkeypatch):
    drone_locations.report_pilot("alpha", 10.31, 123.91, 12.0, "28", "Sam", "13")
    monkeypatch.setattr(drone_locations, "PILOT_STALE_S", -1)
    assert drone_locations.locate("alpha") is None


def _client():
    app = FastAPI()
    app.include_router(drone.router, prefix="/drone")
    app.include_router(responders.router, prefix="/responders")
    return TestClient(app, headers=AUTH_HEADERS)


def test_positions_lists_a_streaming_drone_with_no_position_as_unknown():
    feed_registry.add_feed(source="rtsp://127.0.0.1:8554/live/alpha", label="Alpha", ingest_path="live/alpha")
    (entry,) = _client().get("/drone/positions").json()["drones"]
    assert entry["droneId"] == "alpha"
    assert entry["location"] is None


def test_positions_reports_a_pushed_fix_with_its_accuracy():
    feed_registry.add_feed(source="rtsp://127.0.0.1:8554/live/alpha", label="Alpha", ingest_path="live/alpha")
    client = _client()
    assert client.post("/drone/telemetry", json={"droneId": "alpha", "lat": 10.3, "lng": 123.9,
                                                 "accuracyM": 3, "method": "sdk"}).status_code == 202
    (entry,) = client.get("/drone/positions").json()["drones"]
    assert entry["location"]["source"] == "drone_gps"
    assert entry["location"]["accuracyM"] == 3


def test_a_responder_flying_a_drone_reports_its_position_through_their_phone():
    client = _client()  # signed in as usr-1 (tests/auth_helpers.py)
    client.post("/responders/usr-1/location", json={"lat": 10.31, "lng": 123.91, "accuracy": 8, "pilotOf": "Alpha"})
    loc = drone_locations.locate("alpha")
    assert loc.source == "pilot" and loc.accuracy_m == 8 + drone_locations.PILOT_STANDOFF_M
    # Switching pilot mode off (a fix with no pilotOf) stops standing in for the drone.
    client.post("/responders/usr-1/location", json={"lat": 10.31, "lng": 123.91})
    assert drone_locations.locate("alpha") is None
