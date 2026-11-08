"""
/media — recorded drone footage uploaded by Command Staff, kept for later review.

  POST   /media/upload            store a recorded clip
  GET    /media                   list stored clips (newest first)
  GET    /media/stats             library totals
  GET    /media/{id}              one clip's metadata
  GET    /media/{id}/file         play back the clip (supports Range seeking)
  GET    /media/{id}/thumbnail    poster frame
  POST   /media/{id}/frames       capture a still at a timestamp
  GET    /media/{id}/frames       list captured stills
  GET    /media/{id}/frames/{fid} fetch one captured still
  DELETE /media/{id}              remove clip, frames and index entry

Playback is served here rather than as a static mount so that byte-range
requests work: a browser <video> element seeks by asking for ranges, and
without a 206 response the scrubber cannot move.
"""
from __future__ import annotations

import logging
import mimetypes
import os
from pathlib import Path

from fastapi import APIRouter, Body, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, Response, StreamingResponse

from services import feed_registry as registry
from services import media_store, video_location
from services.responder_registry import haversine_m
from services.feed_registry import FeedLimitReached
from services.media_store import MediaInUse, MediaNotFound, UnsupportedMedia

logger = logging.getLogger("rescueeye.media")
router = APIRouter()

# 1 MiB per chunk — large enough to keep syscall overhead low, small enough
# that a seek to the end of a long clip doesn't buffer the whole file.
_CHUNK = 1024 * 1024


def _parse_range(header: str, size: int) -> tuple[int, int] | None:
    """'bytes=start-end' -> (start, end) inclusive, or None when unusable."""
    if not header or not header.startswith("bytes="):
        return None
    spec = header[len("bytes="):].split(",")[0].strip()
    start_s, _, end_s = spec.partition("-")
    try:
        if not start_s:                      # suffix form: bytes=-500
            length = int(end_s)
            if length <= 0:
                return None
            start, end = max(size - length, 0), size - 1
        else:
            start = int(start_s)
            end = int(end_s) if end_s else size - 1
    except ValueError:
        return None
    if start > end or start >= size:
        return None
    return start, min(end, size - 1)


def _ranged_file_response(path: Path, request: Request, content_type: str) -> Response:
    size = path.stat().st_size
    rng = _parse_range(request.headers.get("range", ""), size)

    if rng is None:
        return FileResponse(path, media_type=content_type,
                            headers={"Accept-Ranges": "bytes"})

    start, end = rng
    length = end - start + 1

    def _iter():
        with path.open("rb") as f:
            f.seek(start)
            remaining = length
            while remaining > 0:
                chunk = f.read(min(_CHUNK, remaining))
                if not chunk:
                    break
                remaining -= len(chunk)
                yield chunk

    return StreamingResponse(
        _iter(),
        status_code=206,
        media_type=content_type,
        headers={
            "Content-Range":  f"bytes {start}-{end}/{size}",
            "Accept-Ranges":  "bytes",
            "Content-Length": str(length),
        },
    )


# ── Upload ────────────────────────────────────────────────────────────────────

# Footage must have been filmed this close to the incident it is filed under.
# A drone surveying a site ranges a few hundred metres from it; past this the
# clip is of somewhere else.
MEDIA_MAX_DISTANCE_M = float(os.getenv("MEDIA_MAX_DISTANCE_M", "1000"))
_MAX_CAPTIONS_BYTES = 20 * 1024 * 1024


def _distance_to(geo: video_location.VideoGeo, lat: float, lng: float) -> float:
    """Closest the footage came to a point: a drone track only has to pass by it."""
    points = [(p[1], p[2]) for p in geo.track] or [(geo.lat, geo.lng)]
    return min(haversine_m(a, b, lat, lng) for a, b in points)


@router.post("/upload", status_code=201)
async def upload_media(
    file: UploadFile = File(...),
    incidentId: str = Form(...),
    incidentLat: float = Form(...),
    incidentLng: float = Form(...),
    droneId: str = Form(...),
    captions: UploadFile | None = File(None),
    simulateLocation: bool = Form(False),
    agencyId: str | None = Form(None),
    uploadedBy: str | None = Form(None),
    uploadedByName: str | None = Form(None),
    note: str = Form(""),
):
    """
    Stores a recorded clip, filed under the incident it was filmed at.

    Where it was filmed is read from the video (services/video_location.py),
    or from DJI's .SRT flight captions uploaded as `captions`. Footage filmed
    more than MEDIA_MAX_DISTANCE_M from the incident is refused, and so is
    footage with no position at all - unless `simulateLocation` is set, which
    places it at the incident and marks it as simulated, for demos.
    """
    if not droneId.strip():
        raise HTTPException(422, "Choose the drone that recorded this video.")
    captions_text = None
    if captions is not None and captions.filename:
        raw = await captions.read(_MAX_CAPTIONS_BYTES + 1)
        if len(raw) > _MAX_CAPTIONS_BYTES:
            raise HTTPException(422, "The caption file is too large to be a DJI .SRT log.")
        captions_text = raw.decode("utf-8", errors="replace")

    def locate(path: Path) -> dict:
        geo = video_location.read_location(path, captions_text)
        if geo is None:
            if not simulateLocation:
                raise UnsupportedMedia(
                    "This video has no GPS location in it, so there is no way to tell it was filmed "
                    "at the incident. For DJI footage, turn on Video Captions in DJI Fly and upload "
                    "the .SRT file with it - or simulate the location for a demo.")
            geo = video_location.simulated_at(incidentLat, incidentLng)
        else:
            distance = _distance_to(geo, incidentLat, incidentLng)
            if distance > MEDIA_MAX_DISTANCE_M:
                raise UnsupportedMedia(
                    f"This video was filmed {distance / 1000:.1f} km from the incident "
                    f"(at {geo.lat:.5f}, {geo.lng:.5f}). Only footage from within "
                    f"{MEDIA_MAX_DISTANCE_M / 1000:g} km of the incident can be filed under it.")
        return geo.to_dict()

    try:
        record = media_store.save_upload(
            file.file,
            file.filename or "upload.mp4",
            content_type=file.content_type or "video/mp4",
            agency_id=agencyId,
            drone_id=droneId,
            uploaded_by=uploadedBy,
            uploaded_by_name=uploadedByName,
            note=note,
            incident_id=incidentId,
            locate=locate,
        )
    except UnsupportedMedia as exc:
        raise HTTPException(422, str(exc))
    return record.to_dict()


# ── Listing ───────────────────────────────────────────────────────────────────

@router.get("")
async def list_media(agencyId: str | None = None, sourceType: str | None = None):
    items = media_store.list_media(agency_id=agencyId, source_type=sourceType)
    return {"items": [m.to_dict() for m in items], "count": len(items)}


@router.get("/stats")
async def media_stats():
    return media_store.stats()


@router.get("/{media_id}")
async def get_media(media_id: str):
    try:
        return media_store.get_media(media_id).to_dict()
    except MediaNotFound as exc:
        raise HTTPException(404, str(exc))


# ── Playback ──────────────────────────────────────────────────────────────────

@router.get("/{media_id}/file")
async def get_media_file(media_id: str, request: Request):
    try:
        path = media_store.media_path(media_id)
        record = media_store.get_media(media_id)
    except MediaNotFound as exc:
        raise HTTPException(404, str(exc))
    guessed = record.content_type or mimetypes.guess_type(path.name)[0] or "video/mp4"
    return _ranged_file_response(path, request, guessed)


@router.get("/{media_id}/thumbnail")
async def get_media_thumbnail(media_id: str):
    try:
        path = media_store.thumbnail_path(media_id)
    except MediaNotFound as exc:
        raise HTTPException(404, str(exc))
    except UnsupportedMedia as exc:
        raise HTTPException(422, str(exc))
    return FileResponse(path, media_type="image/jpeg",
                        headers={"Cache-Control": "public, max-age=3600"})


# ── Captured frames ───────────────────────────────────────────────────────────

@router.post("/{media_id}/frames", status_code=201)
async def capture_media_frame(media_id: str, payload: dict = Body(default={})):
    """Extracts a still at `tSec` and keeps it with the clip for later review."""
    try:
        t = float(payload.get("tSec", 0) or 0)
    except (TypeError, ValueError):
        raise HTTPException(400, "'tSec' must be a number.")
    try:
        frame = media_store.capture_frame(media_id, t, note=str(payload.get("note", "")))
    except MediaNotFound as exc:
        raise HTTPException(404, str(exc))
    except UnsupportedMedia as exc:
        raise HTTPException(422, str(exc))
    return frame.__dict__


@router.get("/{media_id}/frames")
async def list_media_frames(media_id: str):
    try:
        record = media_store.get_media(media_id)
    except MediaNotFound as exc:
        raise HTTPException(404, str(exc))
    return {"items": [f.__dict__ for f in record.frames], "count": len(record.frames)}


@router.get("/{media_id}/frames/{frame_id}")
async def get_media_frame(media_id: str, frame_id: str):
    try:
        path = media_store.frame_path(media_id, frame_id)
    except MediaNotFound as exc:
        raise HTTPException(404, str(exc))
    return FileResponse(path, media_type="image/jpeg",
                        headers={"Cache-Control": "public, max-age=3600"})


# ── Hand-off to Live Monitoring ───────────────────────────────────────────────

@router.post("/{media_id}/monitor", status_code=201)
async def monitor_media(media_id: str):
    """
    Opens a stored clip as a feed so it plays on Live Monitoring and the AI can
    run against it, exactly as a live drone feed would.

    The feed is created from the file's path on the server rather than having
    the browser supply one — the media id is the only handle a client needs,
    and the on-disk layout stays private to the API.

    Re-monitoring a clip that is already open returns the existing feed instead
    of opening a duplicate panel for the same footage.
    """
    try:
        path = media_store.media_path(media_id)
        record = media_store.get_media(media_id)
    except MediaNotFound as exc:
        raise HTTPException(404, str(exc))

    for feed in registry.list_feeds():
        if feed.source == str(path):
            return {"feed": feed.to_dict(), "mediaId": media_id, "reused": True}

    try:
        feed = registry.add_feed(source=str(path), label=record.original_name, kind="upload")
    except FeedLimitReached as exc:
        raise HTTPException(409, str(exc))
    # Detections from this clip are placed where the video says it was filmed.
    feed.media_id = media_id
    feed.media_drone_id = record.drone_id
    feed.geo = video_location.VideoGeo.from_dict(record.geo)
    feed.duration_sec = record.duration_sec
    return {"feed": feed.to_dict(), "mediaId": media_id, "reused": False}


# ── Removal ───────────────────────────────────────────────────────────────────

@router.delete("/{media_id}")
async def delete_media(media_id: str):
    # Close any feed still playing this clip first: on Windows the running
    # FFmpeg process holds the file open, and the unlink would fail.
    try:
        path = str(media_store.media_path(media_id))
        for feed in registry.list_feeds():
            if feed.source == path:
                registry.remove_feed(feed.id)
    except MediaNotFound:
        pass          # no file to release; delete_media below reports the 404

    try:
        media_store.delete_media(media_id)
    except MediaNotFound as exc:
        raise HTTPException(404, str(exc))
    except MediaInUse as exc:
        raise HTTPException(409, str(exc))
    return {"ok": True, "removed": media_id}
