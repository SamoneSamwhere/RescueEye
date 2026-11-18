"""
Standing response teams of Field Responders.

Teams form on their own: when 3-4 available responders are within
TEAM_RADIUS_M of each other, they become a team with a callsign (see
auto_group). Nobody has to form one. When a casualty is verified, the web app
alerts the nearest team with available members. A team that is out on a
mission is kept together until the mission ends, however far its members
spread while travelling; an idle team loses a member who walks away from the
others, and breaks up when fewer than 3 are left.

A commander can still form a team by hand (form); those teams belong to that
commander and auto-grouping leaves their members alone.

Either way a responder is on only one active team in their agency, which is
what stops two commanders being handed the same person.

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

from services.responder_registry import haversine_m

TEAMS_FILE = Path(__file__).parent.parent / "data" / "teams.json"
MAX_TEAM_SIZE = int(os.getenv("MAX_TEAM_SIZE", "8"))
DEFAULT_TEAM_SIZE = int(os.getenv("DEFAULT_TEAM_SIZE", "3"))
CALLSIGNS = ("Alpha", "Bravo", "Charlie", "Delta", "Echo", "Foxtrot", "Golf", "Hotel",
             "India", "Juliet", "Kilo", "Lima", "Mike", "November", "Oscar", "Papa")

# Responders this close to each other are one team.
TEAM_RADIUS_M = float(os.getenv("TEAM_RADIUS_M", "500"))
AUTO_TEAM_MIN = int(os.getenv("AUTO_TEAM_MIN", "3"))
AUTO_TEAM_MAX = int(os.getenv("AUTO_TEAM_MAX", "4"))
# An idle member is dropped only once this far from the rest, so a few metres
# of GPS drift at the edge of the radius does not make a team flicker.
TEAM_LEAVE_M = TEAM_RADIUS_M * 1.5
# Disbanded teams kept in the file, for the record; older ones are pruned.
KEEP_DISBANDED = 200

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


def _check_commander(team: dict, commander_id: str) -> None:
    """A hand-formed team is its commander's to change; an automatic one is any commander's."""
    if not team.get("auto") and team["commanderId"] != str(commander_id):
        raise PermissionError("Only the team's commander can change it.")


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
        _check_commander(team, commander_id)
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
        _check_commander(team, commander_id)
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
        if team.get("auto"):
            raise PermissionError("This team formed on its own from where its responders are. "
                                  "It breaks up when they move apart.")
        if team["commanderId"] != str(commander_id):
            raise PermissionError("Only the team's commander can disband it.")
        team.update(status="DISBANDED", disbandedAt=_now(), updatedAt=_now())
        _write(teams)
        return dict(team)


# -- Automatic teams ----------------------------------------------------------

def _centre(points: list[tuple[float, float]]) -> dict | None:
    if not points:
        return None
    return {"lat": sum(p[0] for p in points) / len(points), "lng": sum(p[1] for p in points) / len(points)}


def _dist(a: tuple[float, float], centre: dict) -> float:
    return haversine_m(a[0], a[1], centre["lat"], centre["lng"])


def auto_group(agency_id: str, positions: dict[str, tuple[float, float, str]], busy: set[str]) -> list[dict]:
    """
    Groups an agency's responders into teams by where they are.

    positions: responder id -> (lat, lng, name), fresh fixes only.
    busy: responder ids on an active mission.

    1. A team with a member on a mission is left as it is.
    2. An idle team drops members who are known to be far from the rest
       (one at a time, farthest first), and breaks up below AUTO_TEAM_MIN.
       A member with no fresh fix stays: unknown is not the same as gone.
    3. Free responders join the nearest idle team with room within the radius.
    4. The rest are grouped: the free responder with the most free neighbours
       within the radius, plus their nearest neighbours up to AUTO_TEAM_MAX,
       becomes a new team when that makes at least AUTO_TEAM_MIN.

    Returns the teams that changed (formed, changed or broken up), so the
    caller can push them to every screen. Hand-formed teams are not touched.
    """
    agency_id = str(agency_id)
    busy = {str(b) for b in busy}
    pos = {str(k): (float(v[0]), float(v[1])) for k, v in positions.items()}
    names = {str(k): str(v[2] or "") for k, v in positions.items()}
    changed: dict[str, dict] = {}

    def member(rid: str) -> dict:
        return {"id": rid, "name": names.get(rid) or f"Responder {rid}"}

    def centre_of(members: list[dict]) -> dict | None:
        return _centre([pos[m["id"]] for m in members if m["id"] in pos])

    with _lock:
        teams = _read()
        idle = []
        for team in teams:
            if team["agencyId"] != agency_id or team["status"] != "ACTIVE" or not team.get("auto"):
                continue
            if any(m["id"] in busy for m in team["members"]):
                continue                                  # out on a mission: keep it together
            members = list(team["members"])
            while True:
                placed = [m for m in members if m["id"] in pos]
                worst, worst_d = None, 0.0
                for m in placed:
                    rest = centre_of([o for o in placed if o is not m])
                    d = _dist(pos[m["id"]], rest) if rest else 0.0
                    if d > worst_d:
                        worst, worst_d = m, d
                if worst is None or worst_d <= TEAM_LEAVE_M:
                    break
                members.remove(worst)
            if len(members) < AUTO_TEAM_MIN:
                team.update(status="DISBANDED", disbandedAt=_now(), updatedAt=_now())
                changed[team["id"]] = team
                continue
            if members != team["members"]:
                team.update(members=members, size=len(members), updatedAt=_now())
                changed[team["id"]] = team
            team["centre"] = centre_of(members) or team.get("centre")
            idle.append(team)

        taken = {m["id"] for t in teams if t["agencyId"] == agency_id and t["status"] == "ACTIVE"
                 for m in t["members"]}
        free = sorted(rid for rid in pos if rid not in busy and rid not in taken)

        # Join a nearby idle team that has room.
        for rid in list(free):
            near = [(t, _dist(pos[rid], t["centre"])) for t in idle
                    if t.get("centre") and len(t["members"]) < AUTO_TEAM_MAX]
            near = [(t, d) for t, d in near if d <= TEAM_RADIUS_M]
            if not near:
                continue
            team = min(near, key=lambda x: x[1])[0]
            team["members"] = team["members"] + [member(rid)]
            team.update(size=len(team["members"]), updatedAt=_now(), centre=centre_of(team["members"]))
            changed[team["id"]] = team
            free.remove(rid)

        # Group what is left. `free` is sorted, so ties go to the lowest id and
        # every run over the same positions gives the same teams.
        while len(free) >= AUTO_TEAM_MIN:
            neighbours = {
                rid: sorted((d, o) for o in free if o != rid
                            for d in [haversine_m(*pos[rid], *pos[o])] if d <= TEAM_RADIUS_M)
                for rid in free
            }
            seed = max(free, key=lambda r: len(neighbours[r]))   # max keeps the first of equals
            if len(neighbours[seed]) + 1 < AUTO_TEAM_MIN:
                break
            ids = [seed] + [o for _, o in neighbours[seed][:AUTO_TEAM_MAX - 1]]
            used = {t["name"] for t in teams if t["agencyId"] == agency_id and t["status"] == "ACTIVE"}
            team = {
                "id": uuid.uuid4().hex[:12], "agencyId": agency_id,
                "name": next((c for c in CALLSIGNS if c not in used), f"{len(used) + 1}"),
                "commanderId": None, "commanderName": "", "auto": True,
                "size": len(ids), "members": [member(r) for r in ids],
                "centre": _centre([pos[r] for r in ids]), "status": "ACTIVE",
                "formedAt": _now(), "updatedAt": _now(),
            }
            teams.append(team)
            changed[team["id"]] = team
            free = [r for r in free if r not in ids]

        if changed:
            gone = [i for i, t in enumerate(teams) if t["status"] != "ACTIVE"]
            drop = set(gone[:max(0, len(gone) - KEEP_DISBANDED)])
            _write([t for i, t in enumerate(teams) if i not in drop])
        return [dict(t) for t in changed.values()]
