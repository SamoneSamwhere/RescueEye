"""
Drone feeds — MJPEG multipart streaming for up to four concurrent sources.

Each feed is an independent entry in `services.feed_registry` with its own
FFmpeg process and frame buffer, so adding an uploaded clip or a live RTSP URL
opens a new panel instead of replacing the one that was already running.

FFmpeg stores native-resolution frames; the MJPEG generator downscales for the
browser. The detection pipeline runs client-side — the browser grabs frames
from each panel and posts them to /detect — so per-feed inference needs nothing
extra here.

The legacy single-feed endpoints (/stream/feed3, /stream/status, /stream/source,
/stream/upload) are kept as aliases onto the primary (oldest) feed: the mobile
app's STREAM_URL and the existing docs still point at them.
"""
import io
import logging
import math
import os
import shutil
import time
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw
from fastapi import APIRouter, Body, File, HTTPException, UploadFile
from fastapi.responses import Response, StreamingResponse

from services import drone_ingest
from services import feed_registry as registry
from services.feed_registry import (
    FeedLimitReached,
    FeedNotFound,
    MAX_FEEDS,
    _downscale_jpeg,
)

logger = logging.getLogger("rescueeye.stream")
router = APIRouter()

UPLOAD_DIR = Path(__file__).parent.parent / "data" / "uploads"
ALLOWED_VIDEO_EXTS = {".mp4", ".mov", ".avi", ".mkv", ".ts", ".webm", ".m4v"}


def _encode_pil(img: Image.Image, quality: int = 75) -> bytes:
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=quality)
    return buf.getvalue()


# ── Synthetic fallback frame ──────────────────────────────────────────────────
def synthetic_frame(tick: int, width: int = 1280, height: int = 720,
                    label: str = "SIM FEED") -> bytes:
    """Placeholder frame for a feed with no playable source. `label` identifies
    which panel it belongs to once several are on screen at once."""
    img_array = np.zeros((height, width, 3), dtype=np.uint8)
    for x in range(0, width, 40):
        img_array[:, x] = [0, 25, 35]
    for y in range(0, height, 40):
        img_array[y, :] = [0, 25, 35]
    cx, cy = width // 2, height // 2
    radius = int(60 + 15 * math.sin(tick * 0.12))
    for dy in range(-radius, radius + 1):
        for dx in range(-radius, radius + 1):
            if dx * dx + dy * dy <= radius * radius:
                px, py = cx + dx, cy + dy
                if 0 <= px < width and 0 <= py < height:
                    dist = math.sqrt(dx * dx + dy * dy)
                    intensity = int(180 * (1 - dist / radius))
                    img_array[py, px] = [0, intensity // 3, intensity]
    img = Image.fromarray(img_array, "RGB")
    draw = ImageDraw.Draw(img)
    ts = time.strftime("%H:%M:%S")
    draw.text((8, 8),           f"{label}  {ts}",                  fill=(0, 212, 255))
    draw.text((8, height - 20), "NO SOURCE FILE — SYNTHETIC MODE", fill=(255, 80, 80))
    scan_y = int((tick * 3) % height)
    draw.line([(0, scan_y), (width, scan_y)], fill=(0, 212, 255, 40), width=1)
    return _encode_pil(img, quality=70)


# Kept for backwards compatibility with anything importing the private name.
_synthetic_frame = synthetic_frame


# ── Lifecycle ─────────────────────────────────────────────────────────────────
def startup():
    """Opens the primary feed from DRONE_FEED_PATH_3, as the single-feed build did."""
    source = os.getenv("DRONE_FEED_PATH_3", "")
    registry.add_feed(source=source, label="Feed 1",
                      kind="live" if source else "synthetic")


def shutdown():
    registry.shutdown_all()


# ── MJPEG generation ──────────────────────────────────────────────────────────
def _mjpeg_generator(feed_id: str):
    boundary = f"--rescueeye_{feed_id}\r\n".encode()
    last_seq = 0
    while True:
        try:
            feed = registry.get_feed(feed_id)
        except FeedNotFound:
            # The feed was removed while a client was still streaming it -
            # ending the generator closes the response cleanly.
            return
        # Wait for a frame this client has not seen yet. The old fixed-interval
        # sleep ran on its own clock: it could sit on a finished frame for most
        # of a frame period before sending it, and re-sent unchanged frames
        # whenever the producer was slower than the timer. Blocking on the
        # producer removes that delay, and the wasted bytes with it.
        frame, seq = feed.wait_for_frame(last_seq)
        if frame is None or seq == last_seq:
            continue                      # timed out - re-check the feed exists
        last_seq = seq
        # Converted on the feed, so every viewer of this feed shares one
        # conversion per frame instead of repeating it per connection.
        display = feed.display_jpeg() or frame
        yield (boundary
               + b"Content-Type: image/jpeg\r\n"
               + b"Content-Length: " + str(len(display)).encode() + b"\r\n\r\n"
               + display + b"\r\n")


def _mjpeg_response(feed_id: str) -> StreamingResponse:
    return StreamingResponse(
        _mjpeg_generator(feed_id),
        media_type=f"multipart/x-mixed-replace; boundary=rescueeye_{feed_id}",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


def _save_upload(file: UploadFile) -> Path:
    ext = Path(file.filename or "").suffix.lower()
    if ext not in ALLOWED_VIDEO_EXTS:
        raise HTTPException(422, f"Unsupported file type '{ext}'. Allowed: {', '.join(sorted(ALLOWED_VIDEO_EXTS))}")
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    dest = UPLOAD_DIR / Path(file.filename).name
    with dest.open("wb") as f:
        shutil.copyfileobj(file.file, f)
    logger.info(f"[stream] Uploaded {dest} ({dest.stat().st_size // 1024} KB)")
    return dest


# ── Multi-feed endpoints ──────────────────────────────────────────────────────
DEFAULT_RTMP_PORT = int(os.getenv("RTMP_LISTEN_PORT", "1935"))


def _source_port(source: str, default: int = DEFAULT_RTMP_PORT) -> int:
    """Port out of an rtmp://host:port/path source."""
    try:
        hostpart = source.split("//", 1)[1].split("/", 1)[0]
        return int(hostpart.rsplit(":", 1)[1])
    except (IndexError, ValueError):
        return default


def _port_in_use(port: int) -> bool:
    """
    Whether an existing feed already listens on this port.

    Deliberately *not* a socket probe. FFmpeg's `-listen 1` accepts exactly one
    connection, so dialling the port to test it consumes the very slot the
    drone needs and kills the feed - the check would cause the failure it
    exists to prevent. The registry already knows every listening feed, so ask
    it instead.
    """
    return any(
        registry._is_listen_source(f.source) and _source_port(f.source) == port
        for f in registry.list_feeds()
    )



def _lan_addresses() -> list[str]:
    """
    This machine's LAN IPv4 addresses, best guess first.

    The pilot has to type a publish URL into the DJI app by hand, and the one
    address that will never work there is the one the dashboard is most likely
    showing them - 127.0.0.1 means "the phone", not "this server". So resolve
    real interface addresses and let the UI show them.
    """
    import socket

    def is_lan(ip: str) -> bool:
        """
        Only addresses a phone on the same Wi-Fi could actually dial.

        Loopback is meaningless to another device; 169.254.x is a link with no
        DHCP; and a VPN adapter (Radmin, Tailscale, Hamachi) hands out a
        routable-looking address on a network the phone is not a member of.
        Offering one of those to the pilot produces a "livestream error" with
        nothing wrong on this end, so they are filtered rather than ranked.
        """
        if ip.startswith(("127.", "169.254.")):
            return False
        if ip.startswith(("192.168.", "10.")):
            return True
        if ip.startswith("172."):
            second = int(ip.split(".")[1])
            return 16 <= second <= 31
        return False

    addrs: list[str] = []
    # A UDP connect to a public address picks the interface that actually
    # carries traffic without sending anything, which beats hostname lookup
    # on machines with several adapters (VPN, WSL, Docker, Hyper-V).
    probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        probe.connect(("8.8.8.8", 80))
        addrs.append(probe.getsockname()[0])
    except Exception:
        pass
    finally:
        probe.close()

    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ip = info[4][0]
            if ip not in addrs:
                addrs.append(ip)
    except Exception:
        pass
    return [ip for ip in addrs if is_lan(ip)]



@router.get("/publish-target")
async def publish_target(port: int = DEFAULT_RTMP_PORT, key: str = "dji", name: str | None = None):
    """
    Where a push-only aircraft should send its stream.

    With always-on ingest (services/drone_ingest.py, mode "server") each drone
    gets its own address from `name`, nothing needs registering, and the feed
    opens by itself when the drone goes live. `publishUrls` are what the pilot
    puts into the drone app, which must name a routable address rather than
    localhost.

    Without it (mode "listener") `listenSource` is what goes to POST
    /stream/feeds - a wildcard bind on one port, armed before the drone goes live.
    """
    addrs = _lan_addresses()
    if drone_ingest.is_running():
        path = drone_ingest.stream_path(name or "drone")
        return {
            "mode":         "server",
            "listenSource": None,
            "publishUrls":  [f"rtmp://{a}:{drone_ingest.RTMP_PORT}/{path}" for a in addrs],
            "addresses":    addrs,
            "port":         drone_ingest.RTMP_PORT,
            "streamPath":   path,
            "streamKey":    path.split("/", 1)[1],
            "live":         path in drone_ingest.status()["live"],
        }
    return {
        "mode":         "listener",
        "listenSource": f"rtmp://0.0.0.0:{port}/live/{key}",
        "publishUrls":  [f"rtmp://{a}:{port}/live/{key}" for a in addrs],
        "addresses":    addrs,
        "port":         port,
        "streamKey":    key,
    }


@router.get("/feeds")
async def list_feeds():
    """All active feeds, plus the detection cadence the browser should use."""
    return {
        "feeds":                     [f.to_dict() for f in registry.list_feeds()],
        "max":                       MAX_FEEDS,
        "count":                     registry.count(),
        "suggestedDetectIntervalMs": registry.detect_interval_ms(),
    }


@router.post("/feeds", status_code=201)
async def add_live_feed(payload: dict = Body(...)):
    """Adds a feed from a live URL (rtsp/rtmp/http) or a local file path."""
    source = (payload.get("source") or "").strip()
    label = (payload.get("label") or "").strip() or None
    if not source:
        raise HTTPException(400, "A 'source' URL or path is required.")
    if registry._is_listen_source(source) and _port_in_use(_source_port(source)):
        # Windows lets a second socket bind the same port, so this would
        # otherwise "succeed" and then lose the race for incoming streams to
        # whatever got there first — usually an FFmpeg orphaned by a hard kill
        # of the API. The drone then reports a livestream error while the
        # dashboard shows a healthy feed, which is a miserable thing to debug.
        raise HTTPException(
            409,
            f"Port {_source_port(source)} is already in use. A previous feed may still be "
            "holding it — remove that feed, or end the leftover FFmpeg process, then retry.",
        )
    try:
        feed = registry.add_feed(source=source, label=label, kind="live")
    except FeedLimitReached as exc:
        raise HTTPException(409, str(exc))
    return feed.to_dict()


@router.post("/feeds/upload", status_code=201)
async def add_uploaded_feed(file: UploadFile = File(...), label: str | None = None):
    """Adds a feed from an uploaded video file."""
    # Check capacity before writing the file to disk, so a rejected upload
    # doesn't leave an orphan behind.
    if registry.count() >= MAX_FEEDS:
        raise HTTPException(409, f"Maximum of {MAX_FEEDS} feeds reached — remove one before adding another.")
    dest = _save_upload(file)
    try:
        feed = registry.add_feed(source=str(dest), label=label or dest.stem, kind="upload")
    except FeedLimitReached as exc:
        raise HTTPException(409, str(exc))
    return feed.to_dict()


@router.delete("/feeds/{feed_id}")
async def delete_feed(feed_id: str):
    try:
        registry.remove_feed(feed_id)
    except FeedNotFound:
        raise HTTPException(404, f"No such feed '{feed_id}'")
    from routers.detect import drop_stream
    drop_stream(feed_id)
    return {"ok": True, "removed": feed_id, "count": registry.count()}


@router.get("/feeds/{feed_id}/mjpeg")
async def stream_feed(feed_id: str):
    try:
        registry.get_feed(feed_id)
    except FeedNotFound:
        raise HTTPException(404, f"No such feed '{feed_id}'")
    return _mjpeg_response(feed_id)


@router.post("/feeds/{feed_id}/detect")
async def detect_on_feed(feed_id: str):
    """
    Run detection on this feed's current frame, server-side.

    The browser-side loop costs two round trips per cycle (fetch the snapshot,
    post it back base64-encoded) and can only analyse the downscaled 1280x720
    preview. Detecting here skips both: no image crosses the wire, and the
    model sees the feed's native-resolution frame, which measurably improves
    accuracy on small subjects.

    The client-side path via /detect is unchanged, so anything already using it
    keeps working.
    """
    try:
        feed = registry.get_feed(feed_id)
    except FeedNotFound:
        raise HTTPException(404, f"No such feed '{feed_id}'")
    jpeg = feed.snapshot()
    if jpeg is None:
        raise HTTPException(503, "No frame available yet.")

    # Imported lazily: routers.detect pulls in the model stack, and importing it
    # at module load would make stream.py depend on it for every endpoint here.
    from routers.detect import run_detection
    # Keyed by feed so each one keeps its own tracks and motion history. The
    # result carries frameWidth/frameHeight: boxes are in the analysed frame's
    # pixel space, and the caller renders the MJPEG stream at whatever size.
    try:
        return await run_detection(jpeg, stream_key=feed_id, annotate=False)
    except (ValueError, OSError) as exc:
        raise HTTPException(502, f"Feed frame could not be decoded: {exc}")


@router.get("/feeds/{feed_id}/snapshot")
async def feed_snapshot(feed_id: str):
    try:
        feed = registry.get_feed(feed_id)
    except FeedNotFound:
        raise HTTPException(404, f"No such feed '{feed_id}'")
    frame = feed.snapshot()
    if frame is None:
        return Response(status_code=503, content="No frame available yet")
    try:
        return Response(content=_downscale_jpeg(frame), media_type="image/jpeg")
    except Exception:
        return Response(content=frame, media_type="image/jpeg")


# ── Legacy single-feed endpoints (primary feed) ───────────────────────────────
# The mobile app's STREAM_URL and existing docs point at these.

def _require_primary():
    feed = registry.primary_feed()
    if feed is None:
        raise HTTPException(503, "No feeds are running.")
    return feed


@router.get("/feed3")
async def stream_feed3():
    return _mjpeg_response(_require_primary().id)


@router.post("/source")
async def set_stream_source(payload: dict = Body(...)):
    """
    Replaces the primary feed's source. Retained for the old single-feed
    contract; POST /feeds is what adds a panel.
    """
    source = (payload.get("source") or "").strip()
    primary = registry.primary_feed()
    if primary is not None:
        registry.remove_feed(primary.id)
    feed = registry.add_feed(source=source, label="Feed 1",
                             kind="live" if source else "synthetic")
    return {"ok": True, "source": source or "synthetic", "feedId": feed.id}


@router.post("/upload")
async def upload_drone_feed(file: UploadFile = File(...)):
    """
    Uploads a video and plays it on the primary feed, replacing its source.
    POST /feeds/upload is what adds it as an additional panel instead.
    """
    dest = _save_upload(file)
    primary = registry.primary_feed()
    if primary is not None:
        registry.remove_feed(primary.id)
    feed = registry.add_feed(source=str(dest), label=dest.stem, kind="upload")
    return {"ok": True, "filename": dest.name, "path": str(dest), "feedId": feed.id}


@router.get("/status")
async def stream_status():
    feed = registry.primary_feed()
    return {
        "active":        feed.active if feed else False,
        "fps":           float(os.getenv("FRAME_RATE", "8")),
        "source":        feed.producer if feed else "none",
        "active_source": feed.source if feed else "",
        "has_frame":     bool(feed and feed.current_frame is not None),
        "feedCount":     registry.count(),
        "maxFeeds":      MAX_FEEDS,
    }


@router.get("/snapshot")
async def stream_snapshot():
    return await feed_snapshot(_require_primary().id)
