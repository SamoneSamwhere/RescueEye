"""
Tests for live responder tracking and mission write-back.

The behaviour that matters: a device GPS fix is stored and pushed to every
connected WebSocket client; a later console roster report cannot overwrite a
fresh device fix; mission changes are validated, stored and pushed; and a
client that connects late gets everything current in its snapshot.
"""
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from auth_helpers import AUTH_HEADERS

from routers import live, missions, responders
from services import mission_store, responder_registry


def _build_app() -> FastAPI:
    app = FastAPI()
    app.include_router(responders.router, prefix="/responders")
    app.include_router(missions.router, prefix="/missions")
    app.include_router(live.router, prefix="/live")
    return app


@pytest.fixture
def client():
    responder_registry.reset()
    mission_store.reset()
    yield TestClient(_build_app(), headers=AUTH_HEADERS)
    responder_registry.reset()
    mission_store.reset()


MISSION = {
    "id": "mission-1",
    "incidentId": "incident-1",
    "responderUserId": "usr-1",
    "dispatchedByUserId": "usr-staff",
    "status": "PENDING",
    "dispatchedAt": "2026-10-11T08:00:00.000Z",
}


class TestDeviceLocation:
    def test_fix_is_stored_and_returned(self, client):
        res = client.post("/responders/usr-1/location", json={"lat": 10.31, "lng": 123.89, "name": "Lena"})
        assert res.status_code == 200
        body = res.json()
        assert (body["id"], body["lat"], body["lng"], body["source"]) == ("usr-1", 10.31, 123.89, "device")
        assert body["updatedAt"] > 0

    @pytest.mark.parametrize("payload", [{}, {"lat": "x", "lng": 1}, {"lat": 91, "lng": 0}, {"lat": 0, "lng": 181}])
    def test_bad_coordinates_are_rejected(self, client, payload):
        assert client.post("/responders/usr-1/location", json=payload).status_code == 422

    def test_console_report_cannot_overwrite_fresh_device_fix(self, client):
        client.post("/responders/usr-1/location", json={"lat": 10.31, "lng": 123.89})
        res = client.post("/responders/positions", json={"responders": [{"id": "usr-1", "lat": 1.0, "lng": 2.0}]})
        assert res.json()["accepted"] == 0
        (pos,) = responder_registry.active()
        assert (pos.lat, pos.lng, pos.source) == (10.31, 123.89, "device")

    def test_console_report_still_works_without_a_device_fix(self, client):
        res = client.post("/responders/positions", json={"responders": [{"id": "usr-2", "lat": 1.0, "lng": 2.0}]})
        assert res.json()["accepted"] == 1


class TestMissions:
    def test_put_stores_and_lists(self, client):
        assert client.put("/missions/mission-1", json=MISSION).status_code == 200
        assert client.get("/missions").json() == {"missions": [MISSION]}

    def test_later_state_replaces_earlier(self, client):
        client.put("/missions/mission-1", json=MISSION)
        client.put("/missions/mission-1", json={**MISSION, "status": "EN_ROUTE"})
        (stored,) = client.get("/missions").json()["missions"]
        assert stored["status"] == "EN_ROUTE"

    def test_unknown_status_is_rejected(self, client):
        assert client.put("/missions/mission-1", json={**MISSION, "status": "TELEPORTED"}).status_code == 422

    def test_missing_fields_are_rejected(self, client):
        assert client.put("/missions/mission-1", json={"id": "mission-1", "status": "PENDING"}).status_code == 422

    def test_id_mismatch_is_rejected(self, client):
        assert client.put("/missions/other", json=MISSION).status_code == 422


class TestWebSocket:
    def test_snapshot_includes_current_state(self, client):
        client.post("/responders/usr-1/location", json={"lat": 10.31, "lng": 123.89})
        client.put("/missions/mission-1", json=MISSION)
        with client.websocket_connect("/live/ws") as ws:
            snapshot = ws.receive_json()
        assert snapshot["type"] == "snapshot"
        assert [r["id"] for r in snapshot["responders"]] == ["usr-1"]
        assert snapshot["missions"] == [MISSION]

    def test_snapshot_leaves_out_console_positions(self, client):
        """Console roster positions are not live GPS; the map already has them."""
        client.post("/responders/positions", json={"responders": [{"id": "usr-2", "lat": 1.0, "lng": 2.0}]})
        with client.websocket_connect("/live/ws") as ws:
            assert ws.receive_json()["responders"] == []

    def test_location_and_mission_changes_are_pushed(self, client):
        with client.websocket_connect("/live/ws") as ws:
            ws.receive_json()  # snapshot

            client.post("/responders/usr-1/location", json={"lat": 10.31, "lng": 123.89})
            location = ws.receive_json()
            assert location["type"] == "responder_location"
            assert location["responder"]["id"] == "usr-1"

            client.put("/missions/mission-1", json={**MISSION, "status": "ON_SITE"})
            mission = ws.receive_json()
            assert mission == {"type": "mission", "mission": {**MISSION, "status": "ON_SITE"}}


class TestLocationOverWebSocket:
    def test_fix_sent_up_the_socket_is_stored_and_pushed(self, client):
        with client.websocket_connect("/live/ws") as watcher, client.websocket_connect("/live/ws") as phone:
            watcher.receive_json()
            phone.receive_json()
            phone.send_json({"type": "location", "responderId": "usr-1", "name": "Lena", "lat": 10.31, "lng": 123.89})
            pushed = watcher.receive_json()
        assert pushed["type"] == "responder_location"
        assert (pushed["responder"]["id"], pushed["responder"]["source"]) == ("usr-1", "device")
        (pos,) = responder_registry.active()
        assert (pos.lat, pos.lng) == (10.31, 123.89)

    def test_bad_messages_do_not_close_the_socket(self, client):
        with client.websocket_connect("/live/ws") as ws:
            ws.receive_json()
            ws.send_text("not json")
            ws.send_json({"type": "location", "responderId": "usr-1", "lat": "x", "lng": 1})
            ws.send_json({"type": "something-else"})
            ws.send_json({"type": "location", "responderId": "usr-1", "lat": 10.31, "lng": 123.89})
            assert ws.receive_json()["type"] == "responder_location"
