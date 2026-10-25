"""
Simulated drone flight telemetry.

The platform flies a single feed drone. Until real GPS hardware is integrated,
its position is simulated here — but *coherently*, which the previous approach
was not: `random_coord()` was called once per detection, so two casualties
spotted in the same video frame were reported kilometres apart, and the drone
had no continuous position anything could plot.

This module models one drone flying a smooth wandering track inside the Cebu
City area of interest. Position advances with real elapsed time, so the marker
on the commander's map moves at a plausible speed, and every detection in a
given frame shares the drone's single position at that instant — which is the
physical truth being modelled: the casualty is on the ground below the drone.

Replacing this with real telemetry means swapping `current_position()` for a
read of the flight controller's GPS feed; nothing else needs to change.
"""
import math
import os
import random
import threading
import time
from dataclasses import dataclass

from services import telemetry_sources

# Nominal survey speed for a quadcopter on a search pattern (m/s).
CRUISE_SPEED_MPS = 9.0

# How sharply the track wanders, in radians of heading change per second.
# Small enough to look like a flight path rather than a random walk.
HEADING_DRIFT_RAD_PER_S = 0.25

# When the drone comes within this fraction of the AOI edge, it steers back
# toward the centre instead of leaving the survey area.
EDGE_MARGIN = 0.12

# One degree of latitude in metres. Longitude is scaled by cos(latitude).
METRES_PER_DEG_LAT = 111_320.0

# The demo flight stays over Cebu City.
CEBU_LAT = (10.28, 10.35)
CEBU_LNG = (123.87, 123.92)
LAT_MIN, LAT_MAX = CEBU_LAT
LNG_MIN, LNG_MAX = CEBU_LNG
LAT_CENTRE = (LAT_MIN + LAT_MAX) / 2
LNG_CENTRE = (LNG_MIN + LNG_MAX) / 2


@dataclass
class DroneState:
    drone_id: str
    callsign: str
    lat: float
    lng: float
    heading_rad: float
    speed_mps: float
    updated_at: float
    # Altitude above ground, when the aircraft reports it. None from the
    # simulation, which models a track but not a height.
    altitude_m: float | None = None
    # Which source produced this: 'simulated', 'push' or 'mavlink'. Reported
    # to clients so the UI can label a simulated marker honestly instead of
    # implying a GPS fix the platform does not have.
    source: str = "simulated"
    # Camera pitch below the horizon: 0 = looking straight ahead, -90 = straight
    # down. services/casualty.py needs it because the posture of a body reads
    # completely differently at the two extremes — from nadir a person lying on
    # the ground projects along the image just like a standing person seen from
    # the side, so the same measurement means opposite things. Search flights
    # fly the camera down, which is why the default is nadir.
    gimbal_pitch_deg: float = float(os.getenv("GIMBAL_PITCH_DEG", "-90"))

    @property
    def heading_deg(self) -> float:
        """Compass bearing, 0 = north, clockwise."""
        return (math.degrees(self.heading_rad)) % 360


_lock = threading.Lock()
_state: DroneState | None = None


def _new_state() -> DroneState:
    return DroneState(
        drone_id="DRN-01",
        callsign="Rescue-1",
        lat=LAT_CENTRE,
        lng=LNG_CENTRE,
        heading_rad=random.uniform(0, 2 * math.pi),
        speed_mps=CRUISE_SPEED_MPS,
        updated_at=time.monotonic(),
    )


def _steer_from_edges(state: DroneState) -> float:
    """
    Returns a heading correction that turns the drone back toward the centre
    when it nears the AOI boundary, so the track stays inside the survey area
    without the position ever snapping.
    """
    lat_span = LAT_MAX - LAT_MIN
    lng_span = LNG_MAX - LNG_MIN
    near_edge = (
        state.lat < LAT_MIN + lat_span * EDGE_MARGIN
        or state.lat > LAT_MAX - lat_span * EDGE_MARGIN
        or state.lng < LNG_MIN + lng_span * EDGE_MARGIN
        or state.lng > LNG_MAX - lng_span * EDGE_MARGIN
    )
    if not near_edge:
        return 0.0

    # Bearing from the drone back to the centre of the AOI.
    to_centre = math.atan2(LNG_CENTRE - state.lng, LAT_CENTRE - state.lat)
    # Shortest angular difference, normalised to (-pi, pi].
    delta = (to_centre - state.heading_rad + math.pi) % (2 * math.pi) - math.pi
    # Turn a fraction of the way so the correction reads as a banked turn.
    return delta * 0.35


def _advance(state: DroneState, now: float) -> None:
    dt = now - state.updated_at
    if dt <= 0:
        return
    # A long gap (server idle, no frames processed) would otherwise fling the
    # drone across the map in one step.
    dt = min(dt, 5.0)

    state.heading_rad += random.uniform(-1, 1) * HEADING_DRIFT_RAD_PER_S * dt
    state.heading_rad += _steer_from_edges(state)
    state.heading_rad %= 2 * math.pi

    distance_m = state.speed_mps * dt
    metres_per_deg_lng = METRES_PER_DEG_LAT * math.cos(math.radians(state.lat))

    state.lat += (distance_m * math.cos(state.heading_rad)) / METRES_PER_DEG_LAT
    state.lng += (distance_m * math.sin(state.heading_rad)) / metres_per_deg_lng

    # Hard clamp as a backstop; the edge steering should prevent reaching this.
    state.lat = min(max(state.lat, LAT_MIN), LAT_MAX)
    state.lng = min(max(state.lng, LNG_MIN), LNG_MAX)
    state.updated_at = now


def is_simulated() -> bool:
    """True when no real aircraft has reported recently."""
    return telemetry_sources.live_fix() is None


def current_pitch_deg() -> float:
    """
    Camera pitch below the horizon for the active drone.

    Read once per frame by the casualty gate, which picks a different posture
    measurement for nadir and oblique views.
    """
    return current_state().gimbal_pitch_deg


def current_position() -> tuple[float, float]:
    """
    The drone's position right now. Called once per processed frame so every
    detection in that frame shares one coordinate.
    """
    state = current_state()
    return round(state.lat, 6), round(state.lng, 6)


def current_state(drone_id: str | None = None) -> DroneState:
    """
    Full telemetry, for the /drone/telemetry endpoint.

    A real aircraft wins whenever one has reported recently; the simulated
    flight model is the fallback, not the default. Staleness is what decides —
    a link that drops mid-mission degrades to a labelled simulated track rather
    than freezing every subsequent detection at the last known point.
    """
    fix = telemetry_sources.live_fix(drone_id)
    if fix is not None:
        return DroneState(
            drone_id=fix.drone_id,
            callsign=fix.callsign,
            lat=fix.lat,
            lng=fix.lng,
            # Heading is optional upstream; 0 is a safe placeholder because it
            # is only used for display until georeferencing needs it.
            heading_rad=math.radians(fix.heading_deg or 0.0),
            speed_mps=fix.speed_mps if fix.speed_mps is not None else 0.0,
            updated_at=fix.received_at,
            altitude_m=fix.altitude_m,
            source=fix.source,
            gimbal_pitch_deg=(fix.gimbal_pitch_deg
                              if getattr(fix, "gimbal_pitch_deg", None) is not None
                              else float(os.getenv("GIMBAL_PITCH_DEG", "-90"))),
        )

    return simulated_state()


def simulated_state() -> DroneState:
    """
    The built-in flight model's current position. Demo mode only in anything
    that reaches the map (services/drone_locations.py): it is not a drone.
    """
    global _state
    with _lock:
        if _state is None:
            _state = _new_state()
        _advance(_state, time.monotonic())
        # Return a copy so callers can't mutate the live state.
        return DroneState(**vars(_state))


def reset(lat: float | None = None, lng: float | None = None) -> None:
    """Resets the simulated flight. Used by tests and the demo seed."""
    global _state
    with _lock:
        _state = _new_state()
        if lat is not None:
            _state.lat = lat
        if lng is not None:
            _state.lng = lng
