"""Standing response teams (services/team_store.py, routers/teams.py)."""
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from routers import teams
from services import auth, team_store


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(team_store, "TEAMS_FILE", tmp_path / "teams.json")
    app = FastAPI()
    app.include_router(teams.router, prefix="/teams")
    return TestClient(app)


def h(user, role="COMMAND_STAFF", agency="7"):
    return {"Authorization": f"Bearer {auth.issue_token(user, role, agency)}"}


def form(client, commander, ids, **kw):
    return client.post("/teams", headers=h(commander), json={
        "commanderName": f"Cmdr {commander}", "members": [{"id": i, "name": f"R{i}"} for i in ids], **kw})


def test_a_commander_forms_a_team_of_three_with_a_callsign(client):
    r = form(client, "30", ["1", "2", "3"])
    assert r.status_code == 201
    t = r.json()
    assert (t["name"], t["size"], [m["id"] for m in t["members"]]) == ("Alpha", 3, ["1", "2", "3"])
    assert form(client, "31", ["4"]).json()["name"] == "Bravo"


def test_one_responder_cannot_be_on_two_teams(client):
    form(client, "30", ["1", "2", "3"])
    r = form(client, "31", ["3", "4"])
    assert r.status_code == 409 and r.json()["detail"]["taken"] == {"3": "Team Alpha"}


def test_reforming_replaces_the_commanders_own_team(client):
    first = form(client, "30", ["1", "2", "3"]).json()
    again = form(client, "30", ["2", "3", "4"]).json()       # 2 and 3 are already theirs: no conflict
    assert again["id"] == first["id"] and len(client.get("/teams", headers=h("30")).json()["teams"]) == 1


def test_replace_a_member_who_declined(client):
    t = form(client, "30", ["1", "2", "3"]).json()
    r = client.post(f"/teams/{t['id']}/replace", headers=h("30"), json={"oldId": "2", "new": {"id": "9", "name": "R9"}})
    assert [m["id"] for m in r.json()["members"]] == ["1", "3", "9"]


def test_backup_grows_the_team(client):
    t = form(client, "30", ["1", "2", "3"]).json()
    r = client.post(f"/teams/{t['id']}/members", headers=h("30"), json={"members": [{"id": "5", "name": "R5"}]})
    assert (len(r.json()["members"]), r.json()["size"]) == (4, 4)


def test_only_the_commander_changes_their_team_and_teams_stay_in_their_agency(client):
    t = form(client, "30", ["1", "2"]).json()
    assert client.delete(f"/teams/{t['id']}", headers=h("31")).status_code == 403
    assert client.get("/teams", headers=h("40", agency="8")).json()["teams"] == []
    assert client.delete(f"/teams/{t['id']}", headers=h("30")).json()["status"] == "DISBANDED"
    assert form(client, "31", ["1"]).status_code == 201      # free again once disbanded


def test_a_responder_sees_their_own_team(client):
    form(client, "30", ["1", "2"])
    mine = client.get("/teams/mine", headers=h("2", role="FIELD_RESPONDER")).json()["team"]
    assert mine["name"] == "Alpha" and mine["commanderName"] == "Cmdr 30"

    assert client.post("/teams", headers=h("2", role="FIELD_RESPONDER"), json={"members": []}).status_code == 403


def test_too_many_members_for_the_size(client):
    assert form(client, "30", ["1", "2", "3", "4"], size=3).status_code == 422
