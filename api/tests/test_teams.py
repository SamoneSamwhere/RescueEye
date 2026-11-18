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


# -- Automatic teams (team_store.auto_group) ----------------------------------

BASE = (10.3157, 123.8854)


def at(north_m, east_m=0.0):
    """A point this many metres north/east of BASE."""
    return (BASE[0] + north_m / 111_320, BASE[1] + east_m / 109_550)


def spots(**where):
    return {rid: (*at(*xy), f"R{rid}") for rid, xy in where.items()}


@pytest.fixture()
def store(tmp_path, monkeypatch):
    monkeypatch.setattr(team_store, "TEAMS_FILE", tmp_path / "teams.json")
    return team_store


def ids(team):
    return sorted(m["id"] for m in team["members"])


def test_three_responders_close_together_become_a_team(store):
    changed = store.auto_group("7", spots(a=(0, 0), b=(100, 0), c=(0, 120)), busy=set())
    assert len(changed) == 1
    t = changed[0]
    assert (t["name"], t["auto"], ids(t)) == ("Alpha", True, ["a", "b", "c"])
    assert store.team_of_member("7", "b")["id"] == t["id"]


def test_two_are_not_enough_and_far_ones_are_not_a_team(store):
    assert store.auto_group("7", spots(a=(0, 0), b=(100, 0)), set()) == []
    assert store.auto_group("7", spots(a=(0, 0), b=(2000, 0), c=(4000, 0)), set()) == []


def test_five_close_together_make_a_team_of_four(store):
    t = store.auto_group("7", spots(a=(0, 0), b=(50, 0), c=(100, 0), d=(150, 0), e=(200, 0)), set())
    assert [len(x["members"]) for x in t] == [4]


def test_two_groups_far_apart_are_two_teams(store):
    where = spots(a=(0, 0), b=(80, 0), c=(0, 80), x=(5000, 0), y=(5080, 0), z=(5000, 80), w=(5050, 50))
    teams = store.auto_group("7", where, set())
    assert sorted(map(ids, teams)) == [["a", "b", "c"], ["w", "x", "y", "z"]]
    assert {t["name"] for t in teams} == {"Alpha", "Bravo"}


def test_running_again_with_the_same_positions_changes_nothing(store):
    where = spots(a=(0, 0), b=(100, 0), c=(0, 120))
    first = store.auto_group("7", where, set())[0]
    assert store.auto_group("7", where, set()) == []
    assert store.active_teams("7")[0]["id"] == first["id"]


def test_a_newcomer_joins_the_nearby_team(store):
    store.auto_group("7", spots(a=(0, 0), b=(100, 0), c=(0, 120)), set())
    t = store.auto_group("7", spots(a=(0, 0), b=(100, 0), c=(0, 120), d=(60, 60)), set())[0]
    assert ids(t) == ["a", "b", "c", "d"]


def test_busy_responders_are_not_grouped(store):
    assert store.auto_group("7", spots(a=(0, 0), b=(100, 0), c=(0, 120)), busy={"c"}) == []


def test_an_idle_member_who_walks_away_leaves_and_the_team_breaks_up(store):
    store.auto_group("7", spots(a=(0, 0), b=(100, 0), c=(0, 120), d=(50, 50)), set())
    t = store.auto_group("7", spots(a=(0, 0), b=(100, 0), c=(0, 120), d=(3000, 0)), set())[0]
    assert ids(t) == ["a", "b", "c"]
    t = store.auto_group("7", spots(a=(0, 0), b=(100, 0), c=(4000, 0), d=(3000, 0)), set())[0]
    assert t["status"] == "DISBANDED" and store.active_teams("7") == []


def test_a_team_on_a_mission_stays_together_while_it_travels(store):
    store.auto_group("7", spots(a=(0, 0), b=(100, 0), c=(0, 120)), set())
    assert store.auto_group("7", spots(a=(0, 0), b=(3000, 0), c=(6000, 0)), busy={"b", "c"}) == []
    assert ids(store.active_teams("7")[0]) == ["a", "b", "c"]


def test_a_member_with_no_fresh_fix_is_kept(store):
    store.auto_group("7", spots(a=(0, 0), b=(100, 0), c=(0, 120)), set())
    assert store.auto_group("7", spots(a=(0, 0), b=(100, 0)), set()) == []
    assert ids(store.active_teams("7")[0]) == ["a", "b", "c"]


def test_hand_formed_teams_are_left_alone(store):
    store.form("7", "30", "Cmdr", [{"id": "a", "name": "A"}])
    t = store.auto_group("7", spots(a=(0, 0), b=(100, 0), c=(0, 120), d=(60, 60)), set())[0]
    assert ids(t) == ["b", "c", "d"]


def test_any_commander_can_replace_on_an_automatic_team_but_nobody_disbands_it(client):
    t = team_store.auto_group("7", spots(**{"1": (0, 0), "2": (100, 0), "3": (0, 120)}), set())[0]
    r = client.post(f"/teams/{t['id']}/replace", headers=h("30"), json={"oldId": "2", "new": {"id": "9", "name": "R9"}})
    assert r.status_code == 200 and ids(r.json()) == ["1", "3", "9"]
    assert client.delete(f"/teams/{t['id']}", headers=h("30")).status_code == 403


def test_reading_the_teams_groups_reported_responders(client, monkeypatch):
    from services import mission_store, responder_registry
    responder_registry.reset()
    mission_store.reset()
    for rid, (lat, lng, name) in spots(**{"1": (0, 0), "2": (100, 0), "3": (0, 120)}).items():
        responder_registry.report(rid, lat, lng, name, agency_id="7")
    teams = client.get("/teams", headers=h("30")).json()["teams"]
    assert [ids(t) for t in teams] == [["1", "2", "3"]]
    mine = client.get("/teams/mine", headers=h("2", role="FIELD_RESPONDER")).json()["team"]
    assert mine["name"] == "Alpha"
    responder_registry.reset()
