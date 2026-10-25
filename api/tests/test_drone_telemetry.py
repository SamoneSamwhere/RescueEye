"""
Tests for simulated drone telemetry.

The behaviour that matters is *coherence*: a continuous track at a plausible
speed, staying inside the survey area, with one position per instant. The
previous implementation sampled an independent random coordinate per
detection, which these tests would have caught.
"""
import math
import time

import pytest
from fastapi.testclient import TestClient

from auth_helpers import AUTH_HEADERS

from main import app
from services.detection_store import CEBU_LAT, CEBU_LNG
from services import drone_telemetry


@pytest.fixture(autouse=True)
def fresh_flight():
    drone_telemetry.reset()
    yield
    drone_telemetry.reset()


def _metres_between(a, b):
    dlat = (b[0] - a[0]) * 111_320.0
    dlng = (b[1] - a[1]) * 111_320.0 * math.cos(math.radians(a[0]))
    return math.hypot(dlat, dlng)


class TestFlightPath:
    def test_starts_inside_the_area_of_interest(self):
        state = drone_telemetry.current_state()
        assert CEBU_LAT[0] <= state.lat <= CEBU_LAT[1]
        assert CEBU_LNG[0] <= state.lng <= CEBU_LNG[1]

    def test_position_is_continuous_not_teleporting(self):
        """A casualty map is meaningless if the drone jumps kilometres."""
        previous = drone_telemetry.current_position()
        for _ in range(6):
            time.sleep(0.1)
            current = drone_telemetry.current_position()
            # At 9 m/s, 0.1s of flight is <1m. Allow generous slack for
            # scheduler jitter, but nothing remotely like a random re-roll.
            assert _metres_between(previous, current) < 50
            previous = current

    def test_drone_actually_moves(self):
        start = drone_telemetry.current_position()
        time.sleep(0.4)
        end = drone_telemetry.current_position()
        assert _metres_between(start, end) > 0.5

    def test_stays_within_the_area_of_interest(self):
        """Edge steering must keep a long flight inside the survey box."""
        for _ in range(300):
            state = drone_telemetry.current_state()
            assert CEBU_LAT[0] <= state.lat <= CEBU_LAT[1]
            assert CEBU_LNG[0] <= state.lng <= CEBU_LNG[1]

    def test_an_idle_gap_does_not_fling_the_drone(self):
        """dt is clamped, so a paused server doesn't warp the position."""
        state = drone_telemetry.current_state()
        # Simulate the server having been idle for an hour.
        drone_telemetry._state.updated_at -= 3600
        after = drone_telemetry.current_state()
        # 5s clamp at 9 m/s ≈ 45m ceiling.
        assert _metres_between((state.lat, state.lng), (after.lat, after.lng)) < 100

    def test_reset_recentres_the_flight(self):
        drone_telemetry.reset(lat=10.30, lng=123.88)
        state = drone_telemetry.current_state()
        assert state.lat == pytest.approx(10.30, abs=1e-3)
        assert state.lng == pytest.approx(123.88, abs=1e-3)

    def test_heading_is_a_compass_bearing(self):
        for _ in range(20):
            assert 0 <= drone_telemetry.current_state().heading_deg < 360


class TestTelemetryEndpoint:
    def test_returns_current_position(self):
        client = TestClient(app, headers=AUTH_HEADERS)
        res = client.get("/drone/telemetry")
        assert res.status_code == 200
        body = res.json()
        assert body["droneId"] == "DRN-01"
        assert body["callsign"] == "Rescue-1"
        assert CEBU_LAT[0] <= body["lat"] <= CEBU_LAT[1]
        assert CEBU_LNG[0] <= body["lng"] <= CEBU_LNG[1]

    def test_declares_itself_simulated(self):
        """The UI must be able to label this rather than imply a real GPS fix."""
        client = TestClient(app, headers=AUTH_HEADERS)
        assert client.get("/drone/telemetry").json()["simulated"] is True

    def test_successive_reads_track_smoothly(self):
        client = TestClient(app, headers=AUTH_HEADERS)
        first = client.get("/drone/telemetry").json()
        time.sleep(0.15)
        second = client.get("/drone/telemetry").json()
        assert _metres_between(
            (first["lat"], first["lng"]), (second["lat"], second["lng"])
        ) < 50
