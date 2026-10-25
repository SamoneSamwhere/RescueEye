"""
Sign-in and access control (services/auth.py, routers/auth.py, routers/deps.py).

What must hold: passwords are checked server side and old SHA-256 hashes are
upgraded on sign-in; every protected endpoint refuses a request without a
valid token; and the role and ownership rules hold - a responder reports only
their own location and cannot dispatch.
"""
import hashlib

import jwt
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from routers import alerts, auth as auth_router, missions, responders
from routers.deps import SIGNED_IN
from services import auth, mission_store, responder_registry, supabase_db


def _app() -> FastAPI:
    app = FastAPI()
    app.include_router(auth_router.router, prefix="/auth")
    app.include_router(responders.router, prefix="/responders", dependencies=[SIGNED_IN])
    app.include_router(missions.router, prefix="/missions", dependencies=[SIGNED_IN])
    app.include_router(alerts.router, prefix="/alerts", dependencies=[SIGNED_IN])
    return app


def _bearer(user_id: str, role: str, agency: str = "13") -> dict:
    return {"Authorization": f"Bearer {auth.issue_token(user_id, role, agency)}"}


@pytest.fixture
def client(monkeypatch):
    # Agency "13" is a real (numeric) agency, so missions would be saved to the
    # database; keep these tests off the network.
    async def nothing(*args, **kwargs):
        return None
    monkeypatch.setattr(mission_store, "persist", nothing)
    monkeypatch.setattr(mission_store, "load_agency", nothing)
    responder_registry.reset()
    mission_store.reset()
    yield TestClient(_app())
    responder_registry.reset()
    mission_store.reset()


@pytest.fixture
def users(monkeypatch):
    """An in-memory `user` / `agency` table behind supabase_db."""
    legacy = hashlib.sha256(b"password123").hexdigest()
    rows = {
        "user": [
            {"id": 28, "email": "sam@agency.org", "passwordHash": legacy, "firstName": "Sam", "lastName": "Cortes",
             "role": "FIELD_RESPONDER", "agencyId": 13, "active": True},
            {"id": 40, "email": "off@agency.org", "passwordHash": auth.hash_password("password123"), "firstName": "Off",
             "lastName": "Duty", "role": "COMMAND_STAFF", "agencyId": 13, "active": False},
        ],
        "agency": [{"id": 13, "name": "Mandaue SAR"}],
    }

    async def select_raw(table, params):
        wanted = params["email"].removeprefix("ilike.").replace("\\", "").lower()
        return [r for r in rows[table] if r["email"].lower() == wanted]

    async def select(table, **filters):
        return [r for r in rows[table] if all(r.get(k) == v for k, v in filters.items())]

    async def update(table, row_id, patch):
        for r in rows[table]:
            if r["id"] == row_id:
                r.update(patch)
                return r
        return None

    monkeypatch.setattr(supabase_db, "select_raw", select_raw)
    monkeypatch.setattr(supabase_db, "select", select)
    monkeypatch.setattr(supabase_db, "update", update)
    return rows


class TestPasswords:
    def test_bcrypt_round_trip(self):
        stored = auth.hash_password("correct horse")
        assert stored.startswith("$2b$")
        assert auth.verify_password("correct horse", stored) == (True, False)
        assert auth.verify_password("wrong", stored) == (False, False)

    def test_legacy_hash_matches_and_asks_for_upgrade(self):
        legacy = hashlib.sha256(b"password123").hexdigest()
        assert auth.verify_password("password123", legacy) == (True, True)
        assert auth.verify_password("nope", legacy) == (False, False)

    def test_short_password_is_refused(self):
        assert auth.password_problem("short") is not None
        assert auth.password_problem("long enough") is None


class TestLogin:
    def test_login_returns_session_and_upgrades_legacy_hash(self, client, users):
        res = client.post("/auth/login", json={"email": "SAM@agency.org", "password": "password123"})
        assert res.status_code == 200
        body = res.json()
        assert body["session"] == {"id": "28", "name": "Sam Cortes", "email": "sam@agency.org",
                                   "role": "FIELD_RESPONDER", "agencyId": "13", "agencyName": "Mandaue SAR"}
        assert "passwordHash" not in str(body)
        assert users["user"][0]["passwordHash"].startswith("$2b$")
        principal = auth.read_token(body["token"])
        assert (principal.user_id, principal.role, principal.agency_id) == ("28", "FIELD_RESPONDER", "13")

    def test_wrong_password_and_unknown_email_look_the_same(self, client, users):
        a = client.post("/auth/login", json={"email": "sam@agency.org", "password": "wrong"})
        b = client.post("/auth/login", json={"email": "nobody@agency.org", "password": "wrong"})
        assert a.status_code == b.status_code == 401
        assert a.json() == b.json()

    def test_deactivated_account_cannot_sign_in(self, client, users):
        assert client.post("/auth/login", json={"email": "off@agency.org", "password": "password123"}).status_code == 403

    def test_demo_login_is_off_unless_demo_mode(self, client, monkeypatch):
        monkeypatch.setenv("DEMO_MODE", "false")
        assert client.post("/auth/demo", json={"id": "usr-x", "role": "COMMAND_STAFF"}).status_code == 403
        monkeypatch.setenv("DEMO_MODE", "true")
        assert client.post("/auth/demo", json={"id": "usr-x", "role": "COMMAND_STAFF"}).status_code == 200


class TestTokens:
    def test_protected_endpoint_needs_a_token(self, client):
        assert client.get("/missions").status_code == 401

    def test_tampered_or_expired_token_is_refused(self, client):
        token = auth.issue_token("28", "FIELD_RESPONDER", "13")
        forged = jwt.encode({**jwt.decode(token, options={"verify_signature": False}), "app_role": "SYSTEM_ADMIN"},
                            "not-the-secret", algorithm="HS256")
        assert client.get("/missions", headers={"Authorization": f"Bearer {forged}"}).status_code == 401
        expired = jwt.encode({**jwt.decode(token, options={"verify_signature": False}), "exp": 1},
                             auth._secret, algorithm="HS256")
        assert client.get("/missions", headers={"Authorization": f"Bearer {expired}"}).status_code == 401

    def test_token_in_query_works_for_media_urls(self, client):
        token = auth.issue_token("28", "FIELD_RESPONDER", "13")
        assert client.get(f"/missions?token={token}").status_code == 200

    def test_demo_token_dies_when_demo_mode_is_turned_off(self, client, monkeypatch):
        monkeypatch.setenv("DEMO_MODE", "true")
        token = auth.issue_token("usr-x", "COMMAND_STAFF", "agency-1", demo=True)
        monkeypatch.setenv("DEMO_MODE", "false")
        assert client.get("/missions", headers={"Authorization": f"Bearer {token}"}).status_code == 401


class TestOwnership:
    def test_responder_reports_only_their_own_location(self, client):
        sam = _bearer("28", "FIELD_RESPONDER")
        assert client.post("/responders/28/location", json={"lat": 10.3, "lng": 123.9}, headers=sam).status_code == 200
        assert client.post("/responders/26/location", json={"lat": 10.3, "lng": 123.9}, headers=sam).status_code == 403

    def test_responder_cannot_dispatch(self, client):
        res = client.post("/alerts/dispatch", json={"incidentId": 4, "recipientIds": [28], "dispatchedBy": 30},
                          headers=_bearer("28", "FIELD_RESPONDER"))
        assert res.status_code == 403

    def test_responder_sees_only_their_own_alerts(self, client):
        assert client.get("/alerts?recipientId=26", headers=_bearer("28", "FIELD_RESPONDER")).status_code == 403

    def test_responder_cannot_create_or_reassign_missions(self, client):
        mission = {"id": "m1", "incidentId": "4", "responderUserId": "28", "dispatchedByUserId": "30",
                   "status": "PENDING", "dispatchedAt": "2026-10-25T08:00:00Z"}
        sam = _bearer("28", "FIELD_RESPONDER")
        assert client.put("/missions/m1", json=mission, headers=sam).status_code == 403
        assert client.put("/missions/m1", json=mission, headers=_bearer("30", "COMMAND_STAFF")).status_code == 200
        assert client.put("/missions/m1", json={**mission, "status": "ACCEPTED"}, headers=sam).status_code == 200
        stolen = {**mission, "responderUserId": "26"}
        assert client.put("/missions/m1", json=stolen, headers=sam).status_code == 403

    def test_other_agency_cannot_see_or_touch_missions(self, client):
        mission = {"id": "m1", "incidentId": "4", "responderUserId": "28", "dispatchedByUserId": "30",
                   "status": "PENDING", "dispatchedAt": "2026-10-25T08:00:00Z"}
        client.put("/missions/m1", json=mission, headers=_bearer("30", "COMMAND_STAFF", "13"))
        other = _bearer("99", "COMMAND_STAFF", "12")
        assert client.get("/missions", headers=other).json() == {"missions": []}
        assert client.put("/missions/m1", json=mission, headers=other).status_code == 403
