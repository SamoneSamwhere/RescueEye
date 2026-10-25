"""
Known positions of the agency's own responders.

The most embarrassing false positive in a live operation is the system
flagging the rescue team as casualties. The detector cannot tell them apart —
a rescuer on the ground is a person like any other — but the system already
knows where its responders are, because they report position for the map.

So this is a context filter, not a vision one: a person detected within a few
metres of a responder's last known position is almost certainly that
responder. It suppresses nothing on its own; `services/casualty.py` uses it to
veto the casualty promotion, and the detection is still reported as a person.

Positions are held in memory with a TTL. A stale fix is worse than none here:
a responder who moved 200m ten minutes ago would otherwise keep vetoing
casualties at a location they have long left.

A position has a source. "device" is the responder's own phone GPS, posted by
the Field Responder app; "console" is the last location the Command Staff
console has on record for them. A fresh device fix always wins: the console
reposts its roster every 30s, and must not drag a moving responder back to
where their profile says they are.
"""
from __future__ import annotations

import math
import os
import threading
import time
from dataclasses import dataclass

# How far from a responder's reported position a person still reads as "that
# responder". Covers civilian GPS error (~5m) plus the distance they can cover
# between position reports.
RESPONDER_EXCLUSION_M = float(os.getenv("RESPONDER_EXCLUSION_M", "15"))
RESPONDER_TTL_S       = float(os.getenv("RESPONDER_TTL_S", "120"))

EARTH_RADIUS_M = 6_371_000.0


@dataclass
class ResponderPosition:
    responder_id: str
    lat: float
    lng: float
    reported_at: float  # time.monotonic()
    name: str = ""
    source: str = "console"  # "device" (phone GPS) or "console" (roster)
    updated_at: float = 0.0  # time.time(), for clients that show when it was taken
    agency_id: str | None = None  # whose responder this is; live updates stay within it


_positions: dict[str, ResponderPosition] = {}
_lock = threading.Lock()


def haversine_m(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Great-circle distance in metres."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(min(1.0, math.sqrt(a)))


def report(responder_id: str, lat: float, lng: float, name: str = "",
           source: str = "console", agency_id: str | None = None) -> ResponderPosition | None:
    """
    Records or refreshes one responder's position.

    Returns the stored position, or None when a console report was ignored
    because the responder's own device has reported within the TTL.
    """
    now = time.monotonic()
    with _lock:
        current = _positions.get(responder_id)
        if (source == "console" and current is not None and current.source == "device"
                and now - current.reported_at <= RESPONDER_TTL_S):
            return None
        position = ResponderPosition(
            responder_id=responder_id, lat=lat, lng=lng,
            reported_at=now, name=name or (current.name if current else ""),
            source=source, updated_at=time.time(),
            agency_id=agency_id if agency_id is not None else (current.agency_id if current else None),
        )
        _positions[responder_id] = position
        return position


def active(agency_id: str | None = None) -> list[ResponderPosition]:
    """Positions still within the TTL (of one agency, if given), expiring stale ones as it goes."""
    now = time.monotonic()
    with _lock:
        fresh = {k: v for k, v in _positions.items() if now - v.reported_at <= RESPONDER_TTL_S}
        _positions.clear()
        _positions.update(fresh)
        values = list(fresh.values())
    return values if agency_id is None else [p for p in values if p.agency_id == str(agency_id)]


def nearest(lat: float | None, lng: float | None) -> tuple[ResponderPosition | None, float]:
    """Closest known responder to a point, and the distance in metres."""
    if lat is None or lng is None:
        return None, math.inf
    best, best_d = None, math.inf
    for pos in active():
        d = haversine_m(lat, lng, pos.lat, pos.lng)
        if d < best_d:
            best, best_d = pos, d
    return best, best_d


def is_known_responder(lat: float | None, lng: float | None,
                       radius_m: float | None = None) -> tuple[bool, str]:
    """
    True when a point falls within the exclusion radius of a known responder.

    Returns the responder's label alongside so the detection can carry a reason
    a human reviewer can check, rather than silently scoring lower.
    """
    limit = RESPONDER_EXCLUSION_M if radius_m is None else radius_m
    pos, dist = nearest(lat, lng)
    if pos is None or dist > limit:
        return False, ""
    return True, (pos.name or pos.responder_id)


def reset(agency_id: str | None = None) -> None:
    """Clears all positions (or one agency's) — test hook, and used when an operation ends."""
    with _lock:
        if agency_id is None:
            _positions.clear()
        else:
            for key in [k for k, v in _positions.items() if v.agency_id == str(agency_id)]:
                del _positions[key]
