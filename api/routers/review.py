"""
Detections awaiting (or after) Command Staff review, saved per agency.

PUT /review/detections/{id}   save a detection's latest state (new, verdict refreshed, verified, rejected)
GET /review/detections        the caller's agency's detections, newest first

The web app creates and reviews detections; this is where they persist, so a
refreshed browser or a second Command Staff screen sees the same queue
(supabase/migrations/08_detections_missions.sql). Demo-mode agencies are not
saved: their detections stay in the browser as before.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Body, Depends, HTTPException

from routers.deps import require_roles
from services import auth, supabase_db

logger = logging.getLogger("rescueeye.review")
router = APIRouter()

STAFF = require_roles("COMMAND_STAFF", "AGENCY_ADMIN")
STATUSES = {"PENDING", "VERIFIED", "REJECTED"}
MAX_LISTED = 500


def _real_agency(user: auth.Principal) -> int | None:
    return int(user.agency_id) if user.agency_id and user.agency_id.isdigit() else None


@router.put("/detections/{detection_id}")
async def save_detection(
    detection_id: str,
    body: dict = Body(...),
    user: auth.Principal = Depends(STAFF),
) -> dict:
    """Body: {"detection": {...src/types/detection.ts...}, "mediaAsset": {...} | null}."""
    detection = body.get("detection")
    if not isinstance(detection, dict) or str(detection.get("id")) != detection_id:
        raise HTTPException(422, "'detection' must be an object whose id matches the URL")
    status = detection.get("validationStatus")
    if status not in STATUSES:
        raise HTTPException(422, f"unknown validationStatus {status!r}")
    detected_at = detection.get("detectedAt")
    if not isinstance(detected_at, str) or not detected_at:
        raise HTTPException(422, "'detectedAt' is required")

    agency = _real_agency(user)
    if agency is None:
        return {"saved": False}  # demo mode: nothing to persist to

    existing = await _run(supabase_db.select("review_detection", id=detection_id))
    if existing and existing[0]["agencyId"] != agency:
        raise HTTPException(403, "This detection belongs to another agency.")
    if existing and existing[0]["validationStatus"] != "PENDING" and status == "PENDING":
        # A late verdict refresh from the live feed must not reopen a reviewed detection.
        return {"saved": False}

    media = body.get("mediaAsset")
    await _run(supabase_db.upsert("review_detection", {
        "id": detection_id,
        "agencyId": agency,
        "validationStatus": status,
        "detectedAt": detected_at,
        "data": detection,
        "mediaAsset": media if isinstance(media, dict) else (existing[0]["mediaAsset"] if existing else None),
        "updatedAt": datetime.now(timezone.utc).isoformat(),
    }))
    return {"saved": True}


@router.get("/detections")
async def list_detections(user: auth.Principal = Depends(STAFF)) -> dict:
    agency = _real_agency(user)
    if agency is None:
        return {"detections": []}
    rows = await _run(supabase_db.select(
        "review_detection", agencyId=agency, order="detectedAt.desc", limit=MAX_LISTED,
    ))
    return {"detections": [{"detection": r["data"], "mediaAsset": r.get("mediaAsset")} for r in rows]}


async def _run(coro):
    try:
        return await coro
    except supabase_db.DatabaseNotConfigured as exc:
        raise HTTPException(503, str(exc)) from exc
    except supabase_db.DatabaseError as exc:
        logger.warning(f"[review] database error: {exc}")
        raise HTTPException(502, "The detection could not be saved. Has migration 08 been run?") from exc
