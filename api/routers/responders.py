"""
POST /responders/positions - where our own responders currently are.
POST /responders/{id}/location - one responder's own device GPS fix.

Fed by the client, which already tracks responder positions to draw them on
the Damage Map. The detector uses it as a veto: a person detected within the
exclusion radius of a known responder is that responder, not a casualty.

Positions are operational state with a short TTL, not records - they are held
in memory and lost on restart, which is correct. A position from before the
last restart is too old to veto anything.

Device fixes are also pushed to the web Damage Map over WebSocket (see
routers/live.py), which is how responder markers move in real time.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Body, Depends, HTTPException

from routers.deps import current_user, require_roles
from services import auth, live_hub, responder_registry

logger = logging.getLogger("rescueeye.responders")
router = APIRouter()


def position_payload(p: responder_registry.ResponderPosition) -> dict:
    """One position as the web client expects it (updatedAt in epoch ms)."""
    return {
        "id": p.responder_id,
        "name": p.name,
        "lat": p.lat,
        "lng": p.lng,
        "source": p.source,
        "updatedAt": int(p.updated_at * 1000),
    }


@router.post("/positions")
async def report_positions(
    payload: dict = Body(...),
    user: auth.Principal = Depends(require_roles("COMMAND_STAFF", "AGENCY_ADMIN")),
) -> dict:
    """
    Records responder positions.

    Body: {"responders": [{"id": "...", "lat": 10.3, "lng": 123.9, "name": "..."}]}
    """
    responders = payload.get("responders")
    if not isinstance(responders, list):
        raise HTTPException(422, "'responders' must be a list")

    accepted = 0
    for entry in responders:
        if not isinstance(entry, dict):
            continue
        rid = str(entry.get("id") or "").strip()
        lat, lng = entry.get("lat"), entry.get("lng")
        if not rid or lat is None or lng is None:
            continue
        try:
            # None means the responder's own device reported more recently; that fix stands.
            if responder_registry.report(rid, float(lat), float(lng), str(entry.get("name") or ""),
                                         agency_id=user.agency_id):
                accepted += 1
        except (TypeError, ValueError):
            # One malformed entry should not reject the rest of the batch: the
            # positions that did parse are still useful this frame.
            logger.debug(f"[responders] skipped malformed entry: {entry!r}")

    return {"accepted": accepted, "active": len(responder_registry.active())}


async def record_device_fix(responder_id: str, payload: dict, user: auth.Principal) -> dict:
    """
    Stores one device GPS fix and pushes it to every live client.

    Shared by the REST endpoint below and the WebSocket (routers/live.py), which
    is how the Field Responder app sends fixes while connected. Raises
    ValueError with a readable message on a bad fix.
    """
    responder_id = str(responder_id or "").strip()
    if not responder_id:
        raise ValueError("responder id is required")
    if responder_id != user.user_id:
        # A device reports its own position, never someone else's.
        raise PermissionError("a device can only report its own location")
    try:
        lat, lng = float(payload["lat"]), float(payload["lng"])
    except (KeyError, TypeError, ValueError):
        raise ValueError("'lat' and 'lng' must be numbers")
    if not (-90 <= lat <= 90 and -180 <= lng <= 180):
        raise ValueError("'lat'/'lng' out of range")

    position = responder_registry.report(
        responder_id, lat, lng, str(payload.get("name") or ""), source="device", agency_id=user.agency_id,
    )
    body = position_payload(position)
    await live_hub.broadcast({"type": "responder_location", "responder": body}, user.agency_id)
    return body


@router.post("/{responder_id}/location")
async def report_device_location(
    responder_id: str, payload: dict = Body(...), user: auth.Principal = Depends(current_user),
) -> dict:
    """
    Records a responder's GPS fix from their own device and pushes it live.
    Fallback for when the app's WebSocket is not connected.

    Body: {"lat": 10.3, "lng": 123.9, "name": "..."}
    """
    try:
        return await record_device_fix(responder_id, payload, user)
    except PermissionError as exc:
        raise HTTPException(403, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.get("")
async def list_positions(user: auth.Principal = Depends(current_user)) -> dict:
    """Currently known responder positions, stale ones already expired."""
    return {
        "responders": [
            {
                "id": p.responder_id,
                "name": p.name,
                "lat": p.lat,
                "lng": p.lng,
            }
            for p in responder_registry.active(user.agency_id)
        ],
        "exclusion_radius_m": responder_registry.RESPONDER_EXCLUSION_M,
        "ttl_s": responder_registry.RESPONDER_TTL_S,
    }


@router.delete("")
async def clear_positions(user: auth.Principal = Depends(require_roles("COMMAND_STAFF", "AGENCY_ADMIN"))) -> dict:
    """Drops every known position of the caller's agency - used when an operation ends."""
    responder_registry.reset(user.agency_id)
    return {"cleared": True}
