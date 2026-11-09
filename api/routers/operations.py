"""
/operations - organizations working the same area (services/operations_registry.py).

  PUT    /operations/mine     share this agency's open incidents and responder positions
  DELETE /operations/mine     stop sharing (the console closed or the operation ended)
  GET    /operations/nearby   other agencies near this agency's open incidents, lead marked
  POST   /operations/demo     place a sample organization near a point (rehearsal)
  DELETE /operations/demo     end the sample organization's operation
"""
from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Body, Depends, HTTPException

from routers.deps import require_roles
from services import auth, operations_registry as ops

router = APIRouter()
COMMAND = require_roles("COMMAND_STAFF", "AGENCY_ADMIN", "SYSTEM_ADMIN")


def _agency(user: auth.Principal) -> str:
    if not user.agency_id:
        raise HTTPException(403, "Only an agency's staff can share or see operations.")
    return str(user.agency_id)


@router.put("/mine")
async def share_operation(payload: dict = Body(...), user: auth.Principal = Depends(COMMAND)):
    """Body: {"agencyName", "incidents": [{id, lat, lng, verifiedAt}], "responders": [{lat, lng, busy}]}."""
    snap = ops.report(_agency(user), str(payload.get("agencyName") or ""),
                      payload.get("incidents"), payload.get("responders"))
    return {"ok": True, "incidents": len(snap.incidents), "responders": len(snap.responders)}


@router.delete("/mine")
async def stop_sharing(user: auth.Principal = Depends(COMMAND)):
    ops.withdraw(_agency(user))
    return {"ok": True}


@router.get("/nearby")
async def nearby_agencies(user: auth.Principal = Depends(COMMAND)):
    return ops.nearby(_agency(user))


def _offset(lat: float, lng: float, east_m: float, north_m: float) -> dict:
    return {"lat": lat + north_m / 111_320,
            "lng": lng + east_m / (111_320 * math.cos(math.radians(lat)))}


@router.post("/demo")
async def place_demo_agency(payload: dict = Body(...), user: auth.Principal = Depends(COMMAND)):
    """
    A sample second organization ~400 m from a point (your incident), for
    rehearsing a multi-agency response. {"lat", "lng", "lead": true} makes it
    the lead (its incident predates yours); false makes it a supporting one.

    Like the demo casualty, it needs no demo mode: it is shown only to the
    agency that placed it, so no other organization ever sees it.
    """
    me = _agency(user)
    try:
        lat, lng = float(payload["lat"]), float(payload["lng"])
    except (KeyError, TypeError, ValueError):
        raise HTTPException(422, "'lat' and 'lng' are required.")
    lead = bool(payload.get("lead", True))
    when = datetime.now(timezone.utc) + (timedelta(days=-1) if lead else timedelta(minutes=1))
    incident = {**_offset(lat, lng, 300, 250), "id": "demo-1", "verifiedAt": when.isoformat()}
    responders = [{**_offset(lat, lng, e, n), "busy": b}
                  for e, n, b in ((260, 180, True), (340, 300, True), (380, 140, True), (-200, 420, False))]
    ops.report(ops.demo_agency_id(me), "Banilad Volunteer Rescue Unit (demo)", [incident], responders,
               demo=True, visible_to=me)
    return ops.nearby(me)


@router.delete("/demo")
async def end_demo_agency(user: auth.Principal = Depends(COMMAND)):
    me = _agency(user)
    ops.withdraw(ops.demo_agency_id(me))
    return ops.nearby(me)
