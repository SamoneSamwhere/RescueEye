"""
Place names for coordinates, for dispatch alerts ("Upper Casili, Casili, Mandaue").

A responder reading "10.37965, 123.93388" on a lock screen still has to open a
map to know where that is; a barangay and city tell them at once which way to
go. Uses OpenStreetMap's Nominatim reverse geocoder: free, no key, and good
down to barangay level in the Philippines.

Best effort by design. The lookup has a short timeout and any failure returns
None, so an alert is never held up or lost because a place name was not found
- the coordinates and map link carry the location either way. Results are
cached per ~10 m cell, and Nominatim's usage policy (an identifying
User-Agent, at most one request a second) is respected.

GEOCODE_ENABLED=false turns it off; GEOCODE_URL points at another Nominatim
server (e.g. a self-hosted one for a deployment with heavy traffic).
"""
from __future__ import annotations

import asyncio
import logging
import os
import time
import unicodedata

import httpx

logger = logging.getLogger("rescueeye.geocode")

ENABLED = os.getenv("GEOCODE_ENABLED", "true").strip().lower() == "true"
URL = os.getenv("GEOCODE_URL", "https://nominatim.openstreetmap.org/reverse").strip()
TIMEOUT_S = 4.0
USER_AGENT = "RescueEye/1.0 (disaster response capstone; dispatch alerts)"
MAX_LENGTH = 48

_cache: dict[tuple[float, float], str | None] = {}
_lock = asyncio.Lock()
_last_request = 0.0


def _ascii(text: str) -> str:
    """'Parañaque' -> 'Paranaque': one non-GSM character would make the whole SMS 70-char segments."""
    return unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii").strip()


def format_place(address: dict) -> str | None:
    """Street or neighbourhood, barangay, city - most specific first, no repeats, SMS-safe."""
    parts: list[str] = []
    for keys in (("road", "neighbourhood", "hamlet"),
                 ("suburb", "village", "quarter", "barangay"),
                 ("city", "town", "municipality", "county")):
        value = next((address[k] for k in keys if address.get(k)), None)
        value = _ascii(value) if value else ""
        if value and value not in parts:
            parts.append(value)
    if not parts:
        return None
    place = ", ".join(parts)
    # Too long for an SMS line: drop the street before cutting anything.
    if len(place) > MAX_LENGTH and len(parts) > 2:
        place = ", ".join(parts[1:])
    return place[:MAX_LENGTH].rstrip(", ")


async def place_name(lat: float, lng: float) -> str | None:
    """'Upper Casili, Casili, Mandaue', or None if it can't be found quickly."""
    if not ENABLED:
        return None
    key = (round(lat, 4), round(lng, 4))
    if key in _cache:
        return _cache[key]
    global _last_request
    async with _lock:
        wait = 1.0 - (time.monotonic() - _last_request)
        if wait > 0:
            await asyncio.sleep(wait)
        _last_request = time.monotonic()
        try:
            async with httpx.AsyncClient(timeout=TIMEOUT_S, headers={"User-Agent": USER_AGENT}) as client:
                res = await client.get(URL, params={"format": "jsonv2", "lat": lat, "lon": lng,
                                                    "zoom": 17, "addressdetails": 1})
            res.raise_for_status()
            place = format_place(res.json().get("address") or {})
        except (httpx.HTTPError, ValueError) as exc:
            logger.info(f"[geocode] no place name for {lat:.5f},{lng:.5f}: {exc}")
            return None  # not cached: the next alert may find it
    _cache[key] = place
    return place
