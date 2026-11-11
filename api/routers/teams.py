"""
/teams - standing response teams, one per Command Staff member (services/team_store.py).

  GET    /teams                         the agency's active teams
  GET    /teams/mine                    a responder's team, or a commander's own
  POST   /teams                         form (or re-form) the caller's team
  POST   /teams/{id}/replace            swap one member for another
  POST   /teams/{id}/members            add backup members
  DELETE /teams/{id}                    disband the caller's team

Every change is pushed over the live socket, so other consoles and the
responders' phones see it at once.
"""
from __future__ import annotations

from fastapi import APIRouter, Body, Depends, HTTPException

from routers.deps import current_user, require_roles
from services import auth, live_hub, team_store

router = APIRouter()
COMMANDER = require_roles("COMMAND_STAFF")


def _agency(user: auth.Principal) -> str:
    if not user.agency_id:
        raise HTTPException(403, "Teams belong to an agency.")
    return str(user.agency_id)


async def _changed(team: dict) -> dict:
    await live_hub.broadcast({"type": "team", "team": team}, team["agencyId"])
    return team


@router.get("")
async def list_teams(user: auth.Principal = Depends(current_user)):
    return {"teams": team_store.active_teams(_agency(user))}


@router.get("/mine")
async def my_team(user: auth.Principal = Depends(current_user)):
    agency = _agency(user)
    team = (team_store.team_of_commander(agency, user.user_id) if user.role == "COMMAND_STAFF"
            else team_store.team_of_member(agency, user.user_id))
    return {"team": team}


@router.post("", status_code=201)
async def form_team(payload: dict = Body(...), user: auth.Principal = Depends(COMMANDER)):
    """Body: {"members": [{id, name}], "size": 3, "centre": {lat, lng, label}, "commanderName"}."""
    try:
        team = team_store.form(_agency(user), user.user_id, str(payload.get("commanderName") or ""),
                               payload.get("members"), size=payload.get("size"), centre=payload.get("centre"))
    except team_store.TeamConflict as exc:
        raise HTTPException(409, {"message": str(exc), "taken": exc.taken})
    except (ValueError, TypeError) as exc:
        raise HTTPException(422, str(exc))
    return await _changed(team)


def _guarded(fn, *args):
    try:
        return fn(*args)
    except team_store.TeamNotFound:
        raise HTTPException(404, "No such active team.")
    except PermissionError as exc:
        raise HTTPException(403, str(exc))
    except team_store.TeamConflict as exc:
        raise HTTPException(409, {"message": str(exc), "taken": exc.taken})


@router.post("/{team_id}/replace")
async def replace_member(team_id: str, payload: dict = Body(...), user: auth.Principal = Depends(COMMANDER)):
    """Body: {"oldId": "...", "new": {id, name}} - "new" may be null to just remove."""
    team = _guarded(team_store.replace_member, _agency(user), team_id, user.user_id,
                    str(payload.get("oldId") or ""), payload.get("new"))
    return await _changed(team)


@router.post("/{team_id}/members")
async def add_members(team_id: str, payload: dict = Body(...), user: auth.Principal = Depends(COMMANDER)):
    team = _guarded(team_store.add_members, _agency(user), team_id, user.user_id, payload.get("members"))
    return await _changed(team)


@router.delete("/{team_id}")
async def disband_team(team_id: str, user: auth.Principal = Depends(COMMANDER)):
    team = _guarded(team_store.disband, _agency(user), team_id, user.user_id)
    return await _changed(team)
