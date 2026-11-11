"""
Standing response teams: each Command Staff member leads one team of Field
Responders (3 by default) for the length of an operation.

The commander forms it once, from the nearest available responders, and
every casualty they verify goes to that team - there is no per-incident
picking any more. A responder can be on only one active team in their agency,
which is what stops two commanders being handed the same person.

Choosing *who* is nearest happens in the web app, which holds every
responder's position (live phone GPS and the roster). This module owns the
rule that has to hold across consoles: one responder, one team.

Kept in data/teams.json beside the media index, so teams outlive an API
restart without a database migration.
"""
from __future__ import annotations

import json
import os
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path

TEAMS_FILE = Path(__file__).parent.parent / "data" / "teams.json"
MAX_TEAM_SIZE = int(os.getenv("MAX_TEAM_SIZE", "8"))
DEFAULT_TEAM_SIZE = int(os.getenv("DEFAULT_TEAM_SIZE", "3"))
CALLSIGNS = ("Alpha", "Bravo", "Charlie", "Delta", "Echo", "Foxtrot", "Golf", "Hotel",
             "India", "Juliet", "Kilo", "Lima", "Mike", "November", "Oscar", "Papa")

_lock = threading.Lock()


class TeamConflict(Exception):
    """Some of the requested members are already on another active team."""
    def __init__(self, taken: dict[str, str]):
        self.taken = taken             # responder id -> team name
        super().__init__("Already on another team: " + ", ".join(f"{k} ({v})" for k, v in taken.items()))


class TeamNotFound(Exception):
    pass


def _read() -> list[dict]:
    try:
        return json.loads(TEAMS_FILE.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return []
    except Exception:
        return []


def _write(teams: list[dict]) -> None:
    TEAMS_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = TEAMS_FILE.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(teams, indent=2), encoding="utf-8")
    os.replace(tmp, TEAMS_FILE)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _clean_members(members) -> list[dict]:
    out, seen = [], set()
    for m in members or []:
        rid = str(m.get("id") if isinstance(m, dict) else m).strip()
        if not rid or rid in seen:
            continue
        seen.add(rid)
        name = str(m.get("name") or "").strip()[:120] if isinstance(m, dict) else ""
        out.append({"id": rid, "name": name or f"Responder {rid}"})
    return out


def active_teams(agency_id: str) -> list[dict]:
    with _lock:
        return [t for t in _read() if t["agencyId"] == str(agency_id) and t["status"] == "ACTIVE"]


def team_of_commander(agency_id: str, commander_id: str) -> dict | None:
    return next((t for t in active_teams(agency_id) if t["commanderId"] == str(commander_id)), None)


def team_of_member(agency_id: str, responder_id: str) -> dict | None:
    return next((t for t in active_teams(agency_id)
                 if any(m["id"] == str(responder_id) for m in t["members"])), None)


def _check_free(teams: list[dict], agency_id: str, member_ids: list[str], except_team: str | None) -> None:
    taken = {}
    for t in teams:
        if t["agencyId"] != agency_id or t["status"] != "ACTIVE" or t["id"] == except_team:
            continue
        for m in t["members"]:
            if m["id"] in member_ids:
                taken[m["id"]] = f"Team {t['name']}"
    if taken:
        raise TeamConflict(taken)


def form(agency_id: str, commander_id: str, commander_name: str, members, *,
         size: int | None = None, centre: dict | None = None) -> dict:
    """
    Forms (or re-forms) this commander's team. A commander leads one team at a
    time; forming again replaces their old one, keeping its callsign.
    """
    agency_id, commander_id = str(agency_id), str(commander_id)
    members = _clean_members(members)
    size = max(1, min(int(size or DEFAULT_TEAM_SIZE), MAX_TEAM_SIZE))
    if len(members) > size:
        raise ValueError(f"A team of {size} cannot have {len(members)} members.")
    with _lock:
        teams = _read()
        current = next((t for t in teams if t["agencyId"] == agency_id and t["status"] == "ACTIVE"
                        and t["commanderId"] == commander_id), None)
        _check_free(teams, agency_id, [m["id"] for m in members], current["id"] if current else None)
        if current:
            current.update(members=members, size=size, centre=centre, updatedAt=_now())
            team = current
        else:
            used = {t["name"] for t in teams if t["agencyId"] == agency_id and t["status"] == "ACTIVE"}
            name = next((c for c in CALLSIGNS if c not in used), f"{len(used) + 1}")
            team = {
                "id": uuid.uuid4().hex[:12], "agencyId": agency_id, "name": name,
                "commanderId": commander_id, "commanderName": (commander_name or "").strip()[:120],
                "size": size, "members": members, "centre": centre, "status": "ACTIVE",
                "formedAt": _now(), "updatedAt": _now(),
            }
            teams.append(team)
        _write(teams)
        return dict(team)


def replace_member(agency_id: str, team_id: str, commander_id: str, old_id: str, new_member) -> dict:
    """Swap one member for another - a decline, or the commander's choice."""
    agency_id = str(agency_id)
    new = _clean_members([new_member])
    with _lock:
        teams = _read()
        team = next((t for t in teams if t["id"] == team_id and t["agencyId"] == agency_id
                     and t["status"] == "ACTIVE"), None)
        if team is None:
            raise TeamNotFound(team_id)
        if team["commanderId"] != str(commander_id):
            raise PermissionError("Only the team's commander can change it.")
        if new:
            _check_free(teams, agency_id, [new[0]["id"]], team["id"])
        kept = [m for m in team["members"] if m["id"] != str(old_id)]
        if new and all(m["id"] != new[0]["id"] for m in kept):
            kept.append(new[0])
        team.update(members=kept, updatedAt=_now())
        _write(teams)
        return dict(team)


def add_members(agency_id: str, team_id: str, commander_id: str, members) -> dict:
    """Backup for a casualty that needs more hands than the team has."""
    agency_id = str(agency_id)
    extra = _clean_members(members)
    with _lock:
        teams = _read()
        team = next((t for t in teams if t["id"] == team_id and t["agencyId"] == agency_id
                     and t["status"] == "ACTIVE"), None)
        if team is None:
            raise TeamNotFound(team_id)
        if team["commanderId"] != str(commander_id):
            raise PermissionError("Only the team's commander can change it.")
        new = [m for m in extra if all(m["id"] != k["id"] for k in team["members"])]
        _check_free(teams, agency_id, [m["id"] for m in new], team["id"])
        team["members"] = team["members"] + new
        team["size"] = max(team["size"], len(team["members"]))
        team["updatedAt"] = _now()
        _write(teams)
        return dict(team)


def disband(agency_id: str, team_id: str, commander_id: str) -> dict:
    with _lock:
        teams = _read()
        team = next((t for t in teams if t["id"] == team_id and t["agencyId"] == str(agency_id)
                     and t["status"] == "ACTIVE"), None)
        if team is None:
            raise TeamNotFound(team_id)
        if team["commanderId"] != str(commander_id):
            raise PermissionError("Only the team's commander can disband it.")
        team.update(status="DISBANDED", disbandedAt=_now(), updatedAt=_now())
        _write(teams)
        return dict(team)
