"""
In-memory circular buffer for recent detections.
Shared across detect, classify, and the /detections/recent endpoint.
Phase 3 will replace this with Firestore persistence.
"""
import io
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Deque

# Cebu City bounding box for simulated GPS coordinates

MAX_STORED = 200


@dataclass
class StoredDetection:
    id: str
    cls: str
    confidence: float
    bbox: dict
    timestamp: str
    # None when nothing knew where the drone was (services/drone_locations.py).
    lat: float | None
    lng: float | None
    inference_time_ms: float
    # Size of the frame the bbox was measured in. Without it a consumer cannot
    # turn pixel boxes into the percentages the review UI draws with, and the
    # frame size varies by source (a 1080p feed vs a 4K upload).
    frame_width: int = 0
    frame_height: int = 0
    # SORT track id: the same physical subject keeps this across frames, so a
    # consumer can collapse a hundred sightings of one casualty into one thing
    # to act on instead of a hundred rows.
    track_id: int | None = None
    # Why the casualty gate promoted this person (services/casualty.py). Stored
    # because the review screen asks a commander to act on the verdict, and a
    # verdict with no reasoning behind it is just a number to take on faith.
    casualty_score: float | None = None
    casualty_reasons: list[str] | None = None
    # What the damage classifier made of the whole frame this subject was seen
    # in — {"label", "confidence", "severity"}, e.g. fire_damage / CRITICAL.
    # A casualty in a burning building and one in an open field are different
    # rescues, and the incident is the only place that difference survives.
    scene: dict | None = None
    # A JPEG crop of the subject, kept in memory alongside the record so the
    # review screen can show what the model actually saw. It rides the same
    # bounded deque, so old crops are evicted with their detection and nothing
    # accumulates on disk.
    snapshot: bytes | None = None
    # Where `lat`/`lng` came from - drone_gps | pilot | simulated - and how far
    # off it may be, so the map can draw the uncertainty instead of a false pin.
    location_source: str | None = None
    location_accuracy_m: float | None = None
    drone_id: str | None = None


# Context kept around the box so a reviewer can see where the subject is,
# as a fraction of the box's own size.
SNAPSHOT_PADDING = 0.6
SNAPSHOT_MAX_EDGE = 360


def _crop_snapshot(frame, bbox: dict) -> bytes | None:
    """JPEG crop around one detection, with context padding. None on failure."""
    try:
        from PIL import Image

        fh, fw = frame.shape[:2]
        pad_x = int(bbox["w"] * SNAPSHOT_PADDING)
        pad_y = int(bbox["h"] * SNAPSHOT_PADDING)
        x1 = max(0, int(bbox["x"]) - pad_x)
        y1 = max(0, int(bbox["y"]) - pad_y)
        x2 = min(fw, int(bbox["x"] + bbox["w"]) + pad_x)
        y2 = min(fh, int(bbox["y"] + bbox["h"]) + pad_y)
        if x2 <= x1 or y2 <= y1:
            return None
        img = Image.fromarray(frame[y1:y2, x1:x2])
        img.thumbnail((SNAPSHOT_MAX_EDGE, SNAPSHOT_MAX_EDGE), Image.BILINEAR)
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=80)
        return buf.getvalue()
    except Exception:
        # A missing thumbnail must never cost us the detection itself.
        return None


_store: Deque[StoredDetection] = deque(maxlen=MAX_STORED)


def add_detections(detections: list[dict], inference_time_ms: float,
                   frame_width: int = 0, frame_height: int = 0,
                   frame=None, scene: dict | None = None) -> None:
    """`scene` is the frame's damage classification, stamped on every detection in it."""
    scene_fields = (
        {k: scene[k] for k in ("label", "confidence", "severity") if k in scene} if scene else None
    )
    for det in detections:
        # The coordinate the detect pass stamped on, or None. This used to
        # invent a random point in Cebu when there was none, which put
        # casualties on streets they were never on.
        lat, lng = det.get("lat"), det.get("lng")
        _store.append(
            StoredDetection(
                id=det.get("id", ""),
                cls=det["class"],
                confidence=det["confidence"],
                bbox=det["bbox"],
                timestamp=det.get("timestamp", datetime.now(timezone.utc).isoformat()),
                lat=lat,
                lng=lng,
                inference_time_ms=inference_time_ms,
                frame_width=frame_width,
                frame_height=frame_height,
                snapshot=_crop_snapshot(frame, det["bbox"]) if frame is not None else None,
                track_id=det.get("track_id"),
                casualty_score=det.get("casualty_score"),
                casualty_reasons=det.get("casualty_reasons"),
                scene=scene_fields,
                location_source=det.get("location_source"),
                location_accuracy_m=det.get("location_accuracy_m"),
                drone_id=det.get("drone_id"),
            )
        )


def get_recent(limit: int = 20) -> list[dict]:
    items = list(_store)[-limit:]
    return [
        {
            "id": d.id,
            "class": d.cls,
            "confidence": d.confidence,
            "bbox": d.bbox,
            "timestamp": d.timestamp,
            "lat": d.lat,
            "lng": d.lng,
            "inference_time_ms": d.inference_time_ms,
            "frame_width": d.frame_width,
            "frame_height": d.frame_height,
            "has_snapshot": d.snapshot is not None,
            "track_id": d.track_id,
            "casualty_score": d.casualty_score,
            "casualty_reasons": d.casualty_reasons,
            "scene": d.scene,
            "location_source": d.location_source,
            "location_accuracy_m": d.location_accuracy_m,
            "drone_id": d.drone_id,
        }
        for d in reversed(items)
    ]


def get_snapshot(detection_id: str) -> bytes | None:
    """JPEG crop for one detection, or None once it has aged out of the buffer."""
    for d in _store:
        if d.id == detection_id:
            return d.snapshot
    return None
