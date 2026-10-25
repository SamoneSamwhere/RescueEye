"""
Request authentication shared by the routers.

Every endpoint except sign-in, sign-up and /health requires a session token
(services/auth.py). It normally arrives as `Authorization: Bearer <token>`.
Media the browser loads by URL - an <img> of the MJPEG feed, a <video>
source, a snapshot - cannot carry a header, so `?token=` is accepted too.
"""
from __future__ import annotations

from typing import Iterable

from fastapi import Depends, HTTPException, Request, WebSocket

from services import auth


def _token_from(headers, query_params) -> str | None:
    header = headers.get("authorization", "")
    if header.lower().startswith("bearer "):
        return header[7:].strip() or None
    return query_params.get("token") or None


def current_user(request: Request) -> auth.Principal:
    token = _token_from(request.headers, request.query_params)
    if not token:
        raise HTTPException(401, "Sign in to use RescueEye.")
    try:
        return auth.read_token(token)
    except auth.InvalidToken as exc:
        raise HTTPException(401, str(exc)) from exc


def websocket_user(ws: WebSocket) -> auth.Principal | None:
    """The principal for a WebSocket handshake, or None if its token is missing or invalid."""
    token = _token_from(ws.headers, ws.query_params)
    if not token:
        return None
    try:
        return auth.read_token(token)
    except auth.InvalidToken:
        return None


def require_roles(*roles: str):
    """A dependency that also checks the caller's role."""
    allowed: Iterable[str] = roles

    def check(user: auth.Principal = Depends(current_user)) -> auth.Principal:
        if user.role not in allowed:
            raise HTTPException(403, "Your role is not allowed to do this.")
        return user

    return check


# Router-level guard: `app.include_router(..., dependencies=[SIGNED_IN])`.
SIGNED_IN = Depends(current_user)


def signed_in_or_device(request: Request) -> auth.Principal | None:
    """
    For endpoints a drone bridge pushes to (POST /drone/telemetry): a script on
    the aircraft's ground station has no user session, so it sends
    `X-Device-Key: <DRONE_INGEST_KEY>` instead. A signed-in user also passes.
    """
    import hmac
    import os

    key = os.getenv("DRONE_INGEST_KEY", "").strip()
    sent = request.headers.get("x-device-key", "")
    if key and sent and hmac.compare_digest(key, sent):
        return None
    return current_user(request)
