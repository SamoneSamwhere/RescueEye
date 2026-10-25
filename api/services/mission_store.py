"""
Latest known state of every mission, as written back by the clients.

The web app owns the mission workflow (which transitions are allowed, who may
make them); this store only records the result of each change so it can be
pushed to every other screen and handed to a page that connects later. Held in
memory for the live snapshot, and saved to the database (see persist /
load_agency below) so a restart does not lose a dispatch's progress.

Missions are stored as the client sends them (camelCase, matching
src/types/mission.ts) so the web app can apply them without translation.
"""
from __future__ import annotations

import threading

VALID_STATUSES = {"PENDING", "ACCEPTED", "DECLINED", "EN_ROUTE", "ON_SITE", "COMPLETED"}
REQUIRED_FIELDS = ("id", "incidentId", "responderUserId", "status", "dispatchedAt")

_missions: dict[str, dict] = {}
_agency: dict[str, str | None] = {}  # mission id -> agency it belongs to
_lock = threading.Lock()


class InvalidMission(ValueError):
    pass


def get(mission_id: str) -> dict | None:
    with _lock:
        return _missions.get(str(mission_id))


def agency_of(mission_id: str) -> str | None:
    with _lock:
        return _agency.get(str(mission_id))


def upsert(mission: dict, agency_id: str | None = None) -> dict:
    """Records a mission's latest state, replacing whatever was held for it."""
    missing = [f for f in REQUIRED_FIELDS if not mission.get(f)]
    if missing:
        raise InvalidMission(f"mission is missing {', '.join(missing)}")
    if mission["status"] not in VALID_STATUSES:
        raise InvalidMission(f"unknown mission status {mission['status']!r}")
    stored = dict(mission)
    with _lock:
        _missions[str(stored["id"])] = stored
        if agency_id is not None or str(stored["id"]) not in _agency:
            _agency[str(stored["id"])] = agency_id
    return stored


def all_missions(agency_id: str | None = None) -> list[dict]:
    with _lock:
        if agency_id is None:
            return list(_missions.values())
        return [m for mid, m in _missions.items() if _agency.get(mid) == str(agency_id)]


def reset() -> None:
    """Test hook."""
    with _lock:
        _missions.clear()
        _agency.clear()
        _loaded_agencies.clear()


# ── Database persistence (supabase/migrations/08_detections_missions.sql) ─────
# Memory stays the working copy - it serves the live snapshot instantly - and
# the database is what survives an API restart. Only real agencies (numeric
# ids) are saved; demo-mode missions stay in memory as before.

import logging  # noqa: E402

logger = logging.getLogger("rescueeye.missions")
_loaded_agencies: set[str] = set()


async def persist(mission: dict, agency_id: str | None) -> None:
    """Saves a mission's latest state. A failed write is logged, never raised: the dispatch already happened."""
    if not agency_id or not str(agency_id).isdigit():
        return
    from services import supabase_db
    try:
        await supabase_db.upsert("mission", {
            "id": str(mission["id"]),
            "agencyId": int(agency_id),
            "status": mission["status"],
            "data": mission,
            "updatedAt": mission.get("updatedAt") or _utc_now(),
        })
    except (supabase_db.DatabaseError, supabase_db.DatabaseNotConfigured) as exc:
        logger.warning(f"[missions] could not save mission {mission.get('id')}: {exc}")


async def load_agency(agency_id: str | None) -> None:
    """Loads an agency's saved missions into memory, once per API run."""
    if not agency_id or not str(agency_id).isdigit() or str(agency_id) in _loaded_agencies:
        return
    from services import supabase_db
    try:
        rows = await supabase_db.select("mission", agencyId=int(agency_id))
    except (supabase_db.DatabaseError, supabase_db.DatabaseNotConfigured) as exc:
        logger.warning(f"[missions] could not load agency {agency_id}'s missions: {exc}")
        return
    with _lock:
        for row in rows:
            # Anything changed since startup is newer than the saved copy.
            _missions.setdefault(str(row["id"]), row["data"])
            _agency.setdefault(str(row["id"]), str(agency_id))
        _loaded_agencies.add(str(agency_id))
    logger.info(f"[missions] loaded {len(rows)} saved mission(s) for agency {agency_id}")


def _utc_now() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()
