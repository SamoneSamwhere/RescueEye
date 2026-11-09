"""Suggested priority and team size (services/casualty_assessment.py)."""
import asyncio

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from routers import detections
from services import auth, casualty_assessment as ca

BURIED = {"confidence": 0.8, "casualtyScore": 0.9, "casualtyReasons": ["partly_buried", "not_moving"],
          "scene": {"label": "structural_damage", "severity": "CRITICAL", "confidence": 0.8}}
WALKING = {"confidence": 0.7, "casualtyScore": 0.4, "casualtyReasons": ["upright", "moving"], "scene": None}


@pytest.fixture(autouse=True)
def no_key(monkeypatch):
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
    ca._cache.clear()


def run(payload):
    return asyncio.run(ca.assess(payload))


def test_rules_send_a_full_team_to_someone_buried_in_a_collapse():
    r = run(BURIED)
    assert (r["priority"], r["responders"], r["source"]) == ("CRITICAL", "4+", "rules")
    assert "partly buried" in r["why"]


def test_rules_keep_a_moving_person_in_the_open_low_key():
    r = run(WALKING)
    assert (r["priority"], r["responders"]) == ("MEDIUM", "1")


def test_flood_needs_three():
    r = run({"casualtyScore": 0.7, "casualtyReasons": ["posture_from_pose"],
             "scene": {"label": "flood_damage", "severity": "MODERATE"}})
    assert (r["priority"], r["responders"]) == ("CRITICAL", "3")


def test_only_facts_are_sent_to_jev(monkeypatch):
    sent = {}

    class FakeClient:
        async def post(self, url, headers, json, timeout):
            sent.update(json)
            return httpx.Response(200, request=httpx.Request("POST", url), json={
                "model": "jev-1.13.0", "answers": {
                    "priority": {"type": "choice", "choice": "HIGH", "confidence": 0.81,
                                 "probabilities": {"LOW": 0.01, "MEDIUM": 0.08, "HIGH": 0.7, "CRITICAL": 0.21}},
                    "responders": {"type": "choice", "choice": "3", "confidence": 0.66,
                                   "probabilities": {"1": 0.02, "2": 0.2, "3": 0.6, "4+": 0.18}}}})

    async def fake_client():
        return FakeClient()

    monkeypatch.setenv("TYPESAFE_API_KEY", "test-key")
    monkeypatch.setattr("services.http_client.get_client", fake_client)
    r = run({**BURIED, "lat": 10.3, "lng": 123.9, "snapshotUrl": "http://x/y.jpg"})
    assert (r["priority"], r["responders"], r["source"], r["model"]) == ("HIGH", "3", "jev", "jev-1.13.0")
    assert set(sent) == {"state", "model", "questions"}
    assert "10.3" not in sent["state"] and "jpg" not in sent["state"]
    assert set(sent["questions"]) == {"priority", "responders"}


def test_jev_failure_falls_back_to_rules(monkeypatch):
    class Broken:
        async def post(self, *a, **k):
            raise httpx.ConnectError("no internet")

    async def broken():
        return Broken()

    monkeypatch.setenv("TYPESAFE_API_KEY", "test-key")
    monkeypatch.setattr("services.http_client.get_client", broken)
    r = run(BURIED)
    assert r["source"] == "rules" and "could not be reached" in r["note"]


def test_endpoint_is_for_command_staff_only():
    app = FastAPI()
    app.include_router(detections.router, prefix="/detections")
    client = TestClient(app)
    def h(role):
        return {"Authorization": f"Bearer {auth.issue_token('1', role, '7')}"}
    assert client.post("/detections/assess", json=BURIED, headers=h("COMMAND_STAFF")).json()["responders"] == "4+"
    assert client.post("/detections/assess", json=BURIED, headers=h("FIELD_RESPONDER")).status_code == 403
