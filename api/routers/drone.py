"""
Drone telemetry.

  GET  /drone/telemetry   where the aircraft is now
  POST /drone/telemetry   push a fix from any drone platform
  GET  /drone/sources     which telemetry paths are configured and live

The POST endpoint is what makes the platform drone-agnostic. No single
protocol reaches every aircraft — a Pixhawk speaks MAVLink, a DJI consumer
drone exposes nothing over its video link, a bespoke airframe may only manage
an HTTP request — so anything able to read a position can forward it here in
a few lines, in any language, without RescueEye needing to know the vendor.

MAVLink aircraft need no bridge at all: set MAVLINK_CONNECTION and the API
reads GLOBAL_POSITION_INT directly.
"""
import time

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from services import drone_locations, feed_registry, telemetry_sources
from services.drone_telemetry import current_state, is_simulated
from services.telemetry_sources import STALE_AFTER_S, TelemetryFix

from routers.deps import current_user, signed_in_or_device

router = APIRouter()


class DroneTelemetry(BaseModel):
    droneId: str
    callsign: str
    lat: float
    lng: float
    headingDeg: float
    speedMps: float
    status: str
    simulated: bool
    # simulated | push | mavlink
    source: str
    altitudeM: float | None = None


class TelemetryIn(BaseModel):
    """
    One position report from an aircraft.

    Only lat/lng are required — plenty of platforms expose nothing else, and
    demanding altitude or heading would lock out the very drones this endpoint
    exists to support. Supply them when you can: georeferencing a detection to
    the casualty rather than the aircraft needs both.
    """
    lat: float = Field(..., ge=-90, le=90)
    lng: float = Field(..., ge=-180, le=180)
    droneId: str = "DRN-01"
    callsign: str = "Rescue-1"
    altitudeM: float | None = Field(default=None, description="Metres above ground")
    accuracyM: float | None = Field(
        default=None, gt=0, le=10_000,
        description="Horizontal accuracy of this fix in metres, if the bridge knows it "
                    "(GPS HDOP x UERE, a Remote ID accuracy class, ...). Shown on the map.",
    )
    method: str | None = Field(
        default=None, pattern=r"^(sdk|remote_id|mavlink|gps|push)$",
        description="How the bridge got the fix: sdk (DJI Mobile SDK), remote_id, mavlink, gps.",
    )
    headingDeg: float | None = Field(default=None, ge=0, lt=360)
    speedMps: float | None = Field(default=None, ge=0)
    gimbalPitchDeg: float | None = Field(
        default=None, ge=-90, le=90,
        description="Camera pitch below the horizon; -90 is straight down. "
                    "The casualty gate measures posture differently overhead "
                    "than obliquely, so reporting it materially changes results.",
    )


@router.get("/telemetry", response_model=DroneTelemetry, dependencies=[Depends(current_user)])
async def get_telemetry(droneId: str | None = None) -> DroneTelemetry:
    """
    Current position of the feed drone.

    `simulated` is reported honestly so the UI can label the marker rather
    than implying a GPS fix the platform does not have.
    """
    state = current_state(droneId)
    return DroneTelemetry(
        droneId=state.drone_id,
        callsign=state.callsign,
        lat=round(state.lat, 6),
        lng=round(state.lng, 6),
        headingDeg=round(state.heading_deg, 1),
        speedMps=round(state.speed_mps, 1),
        status="ACTIVE",
        simulated=state.source == "simulated",
        source=state.source,
        altitudeM=round(state.altitude_m, 1) if state.altitude_m is not None else None,
    )


@router.post("/telemetry", status_code=202, dependencies=[Depends(signed_in_or_device)])
async def push_telemetry(payload: TelemetryIn):
    """
    Accept a fix from any drone platform.

    202 rather than 201: nothing is created, the fix is simply the newest
    known position and supersedes whatever came before it.
    """
    telemetry_sources.push_source().submit(
        TelemetryFix(
            lat=payload.lat,
            lng=payload.lng,
            received_at=time.monotonic(),
            source="push",
            drone_id=payload.droneId,
            callsign=payload.callsign,
            altitude_m=payload.altitudeM,
            heading_deg=payload.headingDeg,
            speed_mps=payload.speedMps,
            gimbal_pitch_deg=payload.gimbalPitchDeg,
            extra={k: v for k, v in (("accuracy_m", payload.accuracyM), ("method", payload.method)) if v},
        )
    )
    return {"ok": True, "droneId": payload.droneId, "staleAfterSeconds": STALE_AFTER_S}


@router.get("/sources", dependencies=[Depends(current_user)])
async def telemetry_sources_status():
    """
    Which telemetry paths exist and whether anything real is currently live.

    Useful during a field setup: it answers "is the drone actually talking to
    us?" without having to infer it from whether the map marker looks right.
    """
    mavlink = telemetry_sources.mavlink_source()
    return {
        "activeSource": current_state().source,
        "simulated": is_simulated(),
        "staleAfterSeconds": STALE_AFTER_S,
        "sources": {
            "push": {
                "available": True,
                "endpoint": "POST /drone/telemetry",
                "dronesReporting": telemetry_sources.push_source().known_drones(),
            },
            "mavlink": {
                "available": mavlink is not None,
                "connection": mavlink.connection if mavlink else None,
                "live": mavlink.latest() is not None if mavlink else False,
            },
            "simulated": {"available": True},
        },
    }


@router.get("/positions", dependencies=[Depends(current_user)])
async def drone_positions() -> dict:
    """
    Every drone that is streaming or reporting a position, for the Damage Map.

    `location` is null when nothing knows where a streaming drone is - the map
    lists it as "location unknown" rather than placing it anywhere.
    """
    feeds = {f.drone_id: f for f in feed_registry.list_feeds() if f.drone_id}
    drones = []
    for drone_id in sorted(set(feeds) | drone_locations.known_drone_ids()):
        feed = feeds.get(drone_id)
        location = drone_locations.locate(drone_id)
        drones.append({
            "droneId": drone_id,
            "label": feed.label if feed else drone_id.replace("-", " ").title(),
            "feedId": feed.id if feed else None,
            "streaming": bool(feed and feed.current_frame is not None),
            "location": location.to_dict() if location else None,
        })
    return {"drones": drones, "pilotStandoffM": drone_locations.PILOT_STANDOFF_M}
