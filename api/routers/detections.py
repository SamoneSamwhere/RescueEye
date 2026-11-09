"""
GET /detections/recent          — last N stored detections, with the drone's
                                  position at the moment of each frame.
GET /detections/{id}/snapshot   — JPEG crop of what the model saw, so a
                                  reviewer can confirm a casualty by eye
                                  rather than trusting a confidence number.
POST /detections/demo           — a made-up casualty near a responder, for
                                  rehearsing the review -> dispatch flow.
POST /detections/assess         — suggested priority and team size for one
                                  casualty (Jev by TypeSafe AI, or rules).
"""
import math
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from fastapi.responses import Response

from routers.deps import require_roles
from services import auth, casualty_assessment, detection_store, responder_registry
from services.detection_store import get_recent, get_snapshot

router = APIRouter()


@router.post("/assess")
async def assess_casualty(
    payload: dict = Body(...),
    user: auth.Principal = Depends(require_roles("COMMAND_STAFF", "AGENCY_ADMIN", "SYSTEM_ADMIN")),
):
    """
    How urgent this casualty is and how many responders it needs - a
    suggestion for Command Staff (services/casualty_assessment.py).

    Body: what the web app knows about the casualty - confidence,
    casualtyScore, casualtyReasons, scene. No image or location is taken.
    """
    return await casualty_assessment.assess(payload)


@router.get("/recent")
async def recent_detections(limit: int = Query(default=20, ge=1, le=100)):
    return {"detections": get_recent(limit)}


@router.get("/{detection_id}/snapshot")
async def detection_snapshot(detection_id: str):
    """
    The crop lives in the same bounded buffer as the detection, so it is gone
    once the detection ages out — a 404 here means "too old", not "no such
    detection". Cached hard because a stored crop never changes.
    """
    jpeg = get_snapshot(detection_id)
    if jpeg is None:
        raise HTTPException(404, f"No snapshot for detection '{detection_id}'")
    return Response(content=jpeg, media_type="image/jpeg",
                    headers={"Cache-Control": "public, max-age=86400"})


# Far enough from the responder that the casualty gate's responder veto
# (responder_registry.RESPONDER_EXCLUSION_M, 15 m) would not have dismissed a
# real one there, and close enough to walk to.
DEMO_DISTANCE_M = 60.0


@router.post("/demo")
async def create_demo_casualty(
    payload: dict | None = Body(default=None),
    user: auth.Principal = Depends(require_roles("COMMAND_STAFF", "AGENCY_ADMIN", "SYSTEM_ADMIN")),
):
    """
    Add a demo casualty ~60 m from a responder, for rehearsing review ->
    verify -> dispatch without a drone in the air.

    Body (all optional): {"responderId": "..."} picks the responder; {"lat",
    "lng"} places it exactly. Otherwise it goes next to the first responder of
    the caller's agency that is reporting a position. It enters the same buffer
    as real detections, so it pops up and reviews like one, marked as a
    simulated position. No incident or push alert is sent: those only follow
    a commander's verification, as for any detection.
    """
    payload = payload or {}
    if payload.get("lat") is not None and payload.get("lng") is not None:
        lat, lng, near = float(payload["lat"]), float(payload["lng"]), None
    else:
        responders = responder_registry.active(user.agency_id)
        wanted = payload.get("responderId")
        if wanted is not None:
            responders = [p for p in responders if p.responder_id == str(wanted)]
        if not responders:
            raise HTTPException(404, "No responder is reporting a position. Open the Field Responder app "
                                     "on a phone (location on), or pass lat/lng.")
        near = responders[0]
        # North-east of the responder, DEMO_DISTANCE_M away.
        d = DEMO_DISTANCE_M / math.sqrt(2)
        lat = near.lat + d / 111_320
        lng = near.lng + d / (111_320 * math.cos(math.radians(near.lat)))

    # A real casualty's crop, when the feeds have produced one, so the card
    # shows a body rather than an empty frame.
    source = next((x for x in reversed(detection_store._store)
                   if x.cls == "casualty" and x.snapshot is not None), None)
    det_id = f"demo-{uuid.uuid4().hex[:8]}"
    detection_store._demos.append(detection_store.StoredDetection(
        id=det_id,
        cls="casualty",
        confidence=0.88,
        bbox=source.bbox if source else {"x": 560, "y": 300, "w": 160, "h": 90},
        timestamp=datetime.now(timezone.utc).isoformat(),
        lat=round(lat, 7),
        lng=round(lng, 7),
        inference_time_ms=0.0,
        frame_width=source.frame_width if source else 1280,
        frame_height=source.frame_height if source else 720,
        # Its own subject: the review screen merges sightings by track id.
        track_id=None,
        casualty_score=0.92,
        casualty_reasons=["posture_from_pose_nadir", "stillness_measured"],
        snapshot=source.snapshot if source else None,
        location_source="simulated",
        location_accuracy_m=5.0,
        drone_id="demo",
    ))
    return {
        "id": det_id, "lat": round(lat, 7), "lng": round(lng, 7),
        "nearResponder": {"id": near.responder_id, "name": near.name, "distanceM": DEMO_DISTANCE_M} if near else None,
    }
