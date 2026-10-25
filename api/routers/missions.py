"""
PUT /missions/{id} - write a mission's latest state back and push it live.
GET /missions      - every mission state held, for a client that needs to catch up.

Every mission change in the web app (dispatch, accept, decline, start
navigation, arrive on-site, rescue complete) is written here as it happens,
then broadcast over WebSocket so Command Staff and the responder see it at once.
"""
from __future__ import annotations

from fastapi import APIRouter, Body, Depends, HTTPException

from routers.deps import current_user
from services import auth, live_hub, mission_store

router = APIRouter()


@router.put("/{mission_id}")
async def put_mission(
    mission_id: str, mission: dict = Body(...), user: auth.Principal = Depends(current_user),
) -> dict:
    if str(mission.get("id")) != mission_id:
        raise HTTPException(422, "mission id in the body does not match the URL")
    await mission_store.load_agency(user.agency_id)
    existing = mission_store.get(mission_id)
    if existing is not None and mission_store.agency_of(mission_id) not in (None, user.agency_id):
        raise HTTPException(403, "This mission belongs to another agency.")
    if user.role == "FIELD_RESPONDER":
        # Responders move their own missions along; Command Staff create them.
        own = existing is not None and str(existing.get("responderUserId")) == user.user_id
        if not own or str(mission.get("responderUserId")) != user.user_id:
            raise HTTPException(403, "You can only update your own missions.")
    elif user.role not in ("COMMAND_STAFF", "AGENCY_ADMIN"):
        raise HTTPException(403, "Your role is not allowed to do this.")
    try:
        stored = mission_store.upsert(mission, user.agency_id)
    except mission_store.InvalidMission as exc:
        raise HTTPException(422, str(exc)) from exc
    await mission_store.persist(stored, user.agency_id)
    await live_hub.broadcast({"type": "mission", "mission": stored}, user.agency_id)
    return stored


@router.get("")
async def list_missions(user: auth.Principal = Depends(current_user)) -> dict:
    await mission_store.load_agency(user.agency_id)
    return {"missions": mission_store.all_missions(user.agency_id)}
