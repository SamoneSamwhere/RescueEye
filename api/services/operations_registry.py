"""
Which agencies are working where - so organizations responding to the same
area can see each other on the map, and who is leading there.

Each agency's incidents and responders otherwise stay within that agency. Here
every Command Staff console shares a summary of its agency's operation: open
incidents (position, when verified) and its responders' positions. No names,
phone numbers or casualty details are kept - only what another organization
needs to avoid working the same street blind.

The lead in an area is the agency with the oldest incident still open there:
the first to verify a casualty and commit to the site. When it closes its
incidents (its teams finished or left), the next agency still working the area
becomes the lead, with nothing to set by hand.

A summary nobody has refreshed for SNAPSHOT_TTL_S is dropped: that console
closed, and a stale picture of who is on site is worse than none.
"""
from __future__ import annotations

import os
import threading
import time
from dataclasses import dataclass, field

from services.responder_registry import haversine_m

AREA_RADIUS_M = float(os.getenv("OPERATIONS_AREA_RADIUS_M", "5000"))
SNAPSHOT_TTL_S = float(os.getenv("OPERATIONS_SNAPSHOT_TTL_S", "120"))


def demo_agency_id(for_agency: str) -> str:
    """Each agency rehearses with its own sample organization, seen by nobody else."""
    return f"demo-for-{for_agency}"


@dataclass
class AgencySnapshot:
    agency_id: str
    name: str
    # [{"id", "lat", "lng", "verifiedAt"}] - open incidents only.
    incidents: list[dict] = field(default_factory=list)
    # [{"lat", "lng", "busy"}] - positions only, no identities.
    responders: list[dict] = field(default_factory=list)
    reported_at: float = field(default_factory=time.monotonic)
    demo: bool = False
    # A sample organization is shown only to the agency that placed it.
    visible_to: str | None = None


_lock = threading.Lock()
_snapshots: dict[str, AgencySnapshot] = {}


def _clean_points(items, keys: tuple[str, ...]) -> list[dict]:
    out = []
    for item in items or []:
        try:
            lat, lng = float(item["lat"]), float(item["lng"])
        except (KeyError, TypeError, ValueError):
            continue
        if not (-90 <= lat <= 90 and -180 <= lng <= 180):
            continue
        point = {"lat": round(lat, 6), "lng": round(lng, 6)}
        for k in keys:
            if k in item:
                point[k] = item[k] if k != "id" else str(item[k])[:64]
        out.append(point)
    return out[:200]


def report(agency_id: str, name: str, incidents, responders, *, demo: bool = False,
           visible_to: str | None = None) -> AgencySnapshot:
    snap = AgencySnapshot(
        agency_id=str(agency_id),
        name=(name or f"Agency {agency_id}").strip()[:120],
        incidents=_clean_points(incidents, ("id", "verifiedAt")),
        responders=[{**p, "busy": bool(p.get("busy"))} for p in _clean_points(responders, ("busy",))],
        demo=demo,
        visible_to=visible_to,
    )
    with _lock:
        _snapshots[snap.agency_id] = snap
    return snap


def withdraw(agency_id: str) -> None:
    with _lock:
        _snapshots.pop(str(agency_id), None)


def _live() -> list[AgencySnapshot]:
    now = time.monotonic()
    with _lock:
        for k in [k for k, s in _snapshots.items() if not s.demo and now - s.reported_at > SNAPSHOT_TTL_S]:
            del _snapshots[k]
        return list(_snapshots.values())


def _near(point: dict, centres: list[dict]) -> bool:
    return any(haversine_m(point["lat"], point["lng"], c["lat"], c["lng"]) <= AREA_RADIUS_M for c in centres)


def nearby(agency_id: str) -> dict:
    """
    The organizations working near this agency's open incidents, with the lead
    marked. Empty while the agency has no open incident: there is no "area".
    """
    agency_id = str(agency_id)
    snaps = {s.agency_id: s for s in _live() if s.visible_to in (None, agency_id)}
    mine = snaps.get(agency_id)
    centres = mine.incidents if mine else []
    if not centres:
        return {"radiusM": AREA_RADIUS_M, "leadAgencyId": None, "agencies": []}

    present = []
    for s in snaps.values():
        incidents = [i for i in s.incidents if _near(i, centres)]
        responders = [r for r in s.responders if _near(r, centres)]
        if s.agency_id != agency_id and not incidents and not responders:
            continue
        present.append((s, incidents, responders))

    def first_open(entry) -> str:
        times = [i.get("verifiedAt") or "" for i in entry[1]]
        return min(times) if times else "9999"

    leaders = sorted((e for e in present if e[1]), key=lambda e: (first_open(e), e[0].agency_id))
    lead_id = leaders[0][0].agency_id if leaders else None

    return {
        "radiusM": AREA_RADIUS_M,
        "leadAgencyId": lead_id,
        "agencies": [
            {
                "agencyId": s.agency_id,
                "name": s.name,
                "isSelf": s.agency_id == agency_id,
                "isLead": s.agency_id == lead_id,
                "demo": s.demo,
                "leadingSince": first_open((s, inc, res)) if inc else None,
                "incidents": [{"lat": i["lat"], "lng": i["lng"], "verifiedAt": i.get("verifiedAt")} for i in inc],
                "responders": res,
            }
            for s, inc, res in sorted(present, key=lambda e: (e[0].agency_id != lead_id, e[0].name))
        ],
    }


def reset() -> None:
    """Test hook."""
    with _lock:
        _snapshots.clear()
