"""
GET /live/ws (WebSocket) - live responder positions and mission status.

On connect the client gets a snapshot of everything currently known, then a
message per change.

The Field Responder app also sends its GPS fixes up this socket:
  {"type": "location", "responderId": "...", "name": "...", "lat": .., "lng": ..}
Mission changes are written through REST (routers/missions.py), which
broadcasts here; so is the location fallback in routers/responders.py.
"""
from __future__ import annotations

import json
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from routers.deps import websocket_user
from routers.responders import position_payload, record_device_fix
from services import auth, live_hub, mission_store, responder_registry

logger = logging.getLogger("rescueeye.live")
router = APIRouter()


@router.websocket("/ws")
async def live_updates(ws: WebSocket) -> None:
    # Browsers cannot set headers on a WebSocket, so the token rides in ?token=.
    user = websocket_user(ws)
    if user is None:
        await ws.close(code=4401, reason="sign in required")
        return
    await mission_store.load_agency(user.agency_id)
    snapshot = {
        "responders": [position_payload(p) for p in responder_registry.active(user.agency_id) if p.source == "device"],
        "missions": mission_store.all_missions(user.agency_id),
    }
    await live_hub.connect(ws, snapshot, user.agency_id)
    try:
        # Reading also keeps the connection open and is how a closed tab is noticed.
        while True:
            await _handle_client_message(await ws.receive_text(), user)
    except WebSocketDisconnect:
        pass
    finally:
        await live_hub.disconnect(ws)


async def _handle_client_message(text: str, user: auth.Principal) -> None:
    """A bad message is logged and dropped; it must not close the socket."""
    try:
        message = json.loads(text)
    except json.JSONDecodeError:
        logger.debug(f"[live] ignored non-JSON message: {text[:80]!r}")
        return
    if not isinstance(message, dict) or message.get("type") != "location":
        return
    try:
        await record_device_fix(message.get("responderId"), message, user)
    except (ValueError, PermissionError) as exc:
        logger.debug(f"[live] ignored bad location: {exc}")
