"""
Pushes live operational updates to every connected web client over WebSocket.

Two kinds of message go out, both as JSON:
  {"type": "responder_location", "responder": {...}}  - a responder's GPS fix
  {"type": "mission", "mission": {...}}               - a mission's latest state

A client that connects is first sent {"type": "snapshot", ...} with every
current position and mission, so a page opened mid-operation is not blank
until the next update happens to arrive.

Every client belongs to the agency its session token names, and a message
only goes to clients of the agency it concerns: one LDRRMO must never see
another's responders, missions or alerts.
"""
from __future__ import annotations

import asyncio
import logging

from fastapi import WebSocket

logger = logging.getLogger("rescueeye.live")

_clients: dict[WebSocket, str | None] = {}
_lock = asyncio.Lock()


async def connect(ws: WebSocket, snapshot: dict, agency_id: str | None) -> None:
    await ws.accept()
    await ws.send_json({"type": "snapshot", **snapshot})
    async with _lock:
        _clients[ws] = agency_id
    logger.info(f"[live] client connected ({len(_clients)} total)")


async def disconnect(ws: WebSocket) -> None:
    async with _lock:
        _clients.pop(ws, None)
    logger.info(f"[live] client disconnected ({len(_clients)} total)")


async def broadcast(message: dict, agency_id: str | None) -> None:
    """
    Sends to every client of `agency_id`; one dead socket must not stop the
    rest getting it. With no agency the message goes nowhere - better silent
    than delivered to the wrong organization.
    """
    if agency_id is None:
        logger.warning(f"[live] dropped a {message.get('type')!r} message with no agency")
        return
    async with _lock:
        clients = [ws for ws, agency in _clients.items() if agency == str(agency_id)]
    dead: list[WebSocket] = []
    for ws in clients:
        try:
            await ws.send_json(message)
        except Exception:  # noqa: BLE001 - any send failure means the socket is gone
            dead.append(ws)
    if dead:
        async with _lock:
            for ws in dead:
                _clients.pop(ws, None)


def client_count() -> int:
    return len(_clients)
