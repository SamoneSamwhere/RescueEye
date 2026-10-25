"""
Where each drone is, from the best source available, with an honest accuracy.

RTMP and RTSP carry pictures, not position: DJI Fly's live stream, an IP
camera's RTSP feed and most drone video links include no GPS at all. So a
drone's position is gathered separately, and this module picks the most
accurate one it currently has, per drone:

  1. drone_gps  The aircraft's own GPS, pushed to POST /drone/telemetry by any
                bridge - MAVLink (ArduPilot/PX4, read directly), a DJI Mobile
                SDK app, a Remote ID receiver, a ground-station script.
                Accuracy is whatever the bridge reports, else a per-method default.
  2. pilot      The pilot's phone, from the Field Responder app with "I'm
                flying <drone>" switched on. The drone is somewhere near the
                pilot, not at the pilot, so the accuracy is the phone's own
                error plus PILOT_STANDOFF_M - a wide circle, shown as such.
  3. simulated  The built-in flight model. Demo mode only: in a real
                deployment a made-up position must never reach the map.

None means the position is unknown, and the map and detections say so rather
than inventing one.

A drone is identified by its stream name: rtmp://host:1935/live/alpha is drone
"alpha", and a telemetry bridge reports with droneId "alpha".
"""
from __future__ import annotations

import os
import threading
import time
from dataclasses import dataclass

from services import auth, telemetry_sources

# How far a drone is assumed to fly from the pilot holding the controller.
# Visual line of sight for a small drone; widen it for long-range flights.
PILOT_STANDOFF_M = float(os.getenv("PILOT_STANDOFF_M", "150"))
PILOT_STALE_S = float(os.getenv("PILOT_STALE_S", "20"))

# Typical horizontal accuracy when a bridge does not report its own.
DEFAULT_ACCURACY_M = {
    "mavlink": 3.0,
    "sdk": 3.0,
    "remote_id": 5.0,
    "push": 5.0,
}


@dataclass(frozen=True)
class DroneLocation:
    drone_id: str
    lat: float
    lng: float
    accuracy_m: float
    source: str                     # 'drone_gps' | 'pilot' | 'simulated'
    method: str                     # e.g. 'mavlink', 'sdk', 'remote_id', 'phone', 'flight-model'
    age_s: float
    altitude_m: float | None = None
    heading_deg: float | None = None
    gimbal_pitch_deg: float | None = None
    pilot_name: str | None = None

    @property
    def can_georeference(self) -> bool:
        """Only the aircraft's own GPS with an altitude can place a subject within the frame."""
        return self.source == "drone_gps" and self.altitude_m is not None

    def to_dict(self) -> dict:
        return {
            "droneId": self.drone_id,
            "lat": round(self.lat, 6),
            "lng": round(self.lng, 6),
            "accuracyM": round(self.accuracy_m, 1),
            "source": self.source,
            "method": self.method,
            "ageS": round(self.age_s, 1),
            "altitudeM": round(self.altitude_m, 1) if self.altitude_m is not None else None,
            "headingDeg": round(self.heading_deg, 1) if self.heading_deg is not None else None,
            "pilotName": self.pilot_name,
        }


@dataclass
class _PilotFix:
    lat: float
    lng: float
    accuracy_m: float
    received_at: float
    pilot_id: str
    pilot_name: str
    agency_id: str | None


_lock = threading.Lock()
_pilots: dict[str, _PilotFix] = {}     # drone id -> latest fix from its pilot's phone


def report_pilot(drone_id: str, lat: float, lng: float, accuracy_m: float | None,
                 pilot_id: str, pilot_name: str, agency_id: str | None) -> None:
    with _lock:
        _pilots[drone_id] = _PilotFix(
            lat=lat, lng=lng,
            accuracy_m=max(accuracy_m or 20.0, 1.0),
            received_at=time.monotonic(),
            pilot_id=pilot_id, pilot_name=pilot_name, agency_id=agency_id,
        )


def stop_piloting(pilot_id: str) -> None:
    with _lock:
        for drone_id in [d for d, f in _pilots.items() if f.pilot_id == pilot_id]:
            del _pilots[drone_id]


def _pilot_fix(drone_id: str) -> _PilotFix | None:
    with _lock:
        fix = _pilots.get(drone_id)
    if fix is None or time.monotonic() - fix.received_at > PILOT_STALE_S:
        return None
    return fix


def locate(drone_id: str, *, allow_simulated: bool | None = None) -> DroneLocation | None:
    """The best current position of one drone, or None if nothing real knows it."""
    now = time.monotonic()
    fix = telemetry_sources.live_fix(drone_id) if drone_id else None
    if fix is not None:
        method = fix.extra.get("method") or fix.source
        accuracy = fix.extra.get("accuracy_m") or DEFAULT_ACCURACY_M.get(method, 5.0)
        return DroneLocation(
            drone_id=drone_id, lat=fix.lat, lng=fix.lng, accuracy_m=float(accuracy),
            source="drone_gps", method=method, age_s=now - fix.received_at,
            altitude_m=fix.altitude_m, heading_deg=fix.heading_deg, gimbal_pitch_deg=fix.gimbal_pitch_deg,
        )

    pilot = _pilot_fix(drone_id)
    if pilot is not None:
        return DroneLocation(
            drone_id=drone_id, lat=pilot.lat, lng=pilot.lng,
            accuracy_m=pilot.accuracy_m + PILOT_STANDOFF_M,
            source="pilot", method="phone", age_s=now - pilot.received_at,
            pilot_name=pilot.pilot_name,
        )

    if allow_simulated is None:
        allow_simulated = auth.demo_mode()
    if allow_simulated:
        from services.drone_telemetry import simulated_state
        state = simulated_state()
        return DroneLocation(
            drone_id=drone_id, lat=state.lat, lng=state.lng, accuracy_m=0.0,
            source="simulated", method="flight-model", age_s=0.0,
            altitude_m=state.altitude_m, heading_deg=state.heading_deg,
            gimbal_pitch_deg=state.gimbal_pitch_deg,
        )
    return None


def known_drone_ids() -> set[str]:
    """Drones some position source has heard from, whether or not they are streaming."""
    with _lock:
        piloted = {d for d, f in _pilots.items() if time.monotonic() - f.received_at <= PILOT_STALE_S}
    return piloted | set(telemetry_sources.push_source().known_drones())


def reset() -> None:
    """Test hook."""
    with _lock:
        _pilots.clear()
