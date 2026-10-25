"""
Always-on drone video ingest.

Connecting a DJI drone used to mean: open Connect Drone, copy an address, type
it into DJI Fly, press Connect *before* the pilot went live (or the app
errored), and give each extra drone its own port by hand. Now a small
streaming server, MediaMTX (https://github.com/bluenviron/mediamtx), runs
alongside the API and is always listening:

  - Each drone streams to rtmp://<this computer>:1935/live/<name>. DJI Fly
    remembers the address, so after the first flight the pilot only presses
    Go Live.
  - This service polls MediaMTX for streams that have started, and opens a
    feed for each one (FFmpeg reads it back over local RTSP), so it appears
    on Live Monitoring on its own, with detection running. When a drone stops
    streaming for INGEST_GRACE_S, its feed closes again.
  - Every drone shares port 1935; only the name in the address differs.

MediaMTX only accepts video *in* from the network; reading it back out is
limited to this computer, so nothing else on the Wi-Fi can watch the feeds.
If the MediaMTX binary is missing (api/bin/mediamtx/, see README), ingest is
off and Connect Drone falls back to the old one-listener-per-port mode.

Config (api/.env):
  INGEST_ENABLED       true (default) / false
  INGEST_RTMP_PORT     1935
  INGEST_RTSP_PORT     8554   local read-back, never exposed
  INGEST_API_PORT      9997   MediaMTX control API, localhost only
  INGEST_GRACE_S       10     how long a dropped stream keeps its panel
  MEDIAMTX_BIN         path to mediamtx(.exe), default api/bin/mediamtx/
"""
from __future__ import annotations

import json
import logging
import os
import re
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

from services import feed_registry as registry

logger = logging.getLogger("rescueeye.ingest")

API_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = API_DIR / "data"

ENABLED = os.getenv("INGEST_ENABLED", "true").strip().lower() == "true"
RTMP_PORT = int(os.getenv("INGEST_RTMP_PORT", "1935"))
RTSP_PORT = int(os.getenv("INGEST_RTSP_PORT", "8554"))
API_PORT = int(os.getenv("INGEST_API_PORT", "9997"))
GRACE_S = float(os.getenv("INGEST_GRACE_S", "10"))
POLL_S = 0.5
APP = "live"  # rtmp://host:1935/live/<name>


_proc: subprocess.Popen | None = None
_stop = threading.Event()
_state_lock = threading.Lock()
_feed_for_path: dict[str, str] = {}     # "live/drone1" -> feed id
_last_seen: dict[str, float] = {}       # path -> monotonic time it was last ready
_dismissed: set[str] = set()            # closed by an operator while still live
_running = False


def binary_path() -> Path:
    configured = os.getenv("MEDIAMTX_BIN", "").strip()
    if configured:
        return Path(configured)
    name = "mediamtx.exe" if sys.platform == "win32" else "mediamtx"
    return API_DIR / "bin" / "mediamtx" / name


def is_running() -> bool:
    # _proc is None when an already-running MediaMTX was adopted (see start).
    return _running and (_proc is None or _proc.poll() is None)


def _api_alive() -> bool:
    try:
        _ready_paths()
        return True
    except (urllib.error.URLError, OSError, ValueError):
        return False


def slugify(name: str) -> str:
    """'DJI Neo 2' -> 'dji-neo-2': the drone's part of the stream address."""
    slug = re.sub(r"[^a-z0-9]+", "-", name.strip().lower()).strip("-")[:40]
    return slug or "drone"


def stream_path(name: str) -> str:
    return f"{APP}/{slugify(name)}"


def _config() -> str:
    """
    MediaMTX settings: RTMP in from anywhere, RTSP out to localhost only, the
    control API on localhost, and everything else (HLS, WebRTC, SRT) off.
    """
    return f"""\
logLevel: warn
api: true
apiAddress: 127.0.0.1:{API_PORT}
metrics: false
pprof: false
playback: false
hls: false
webrtc: false
srt: false
rtsp: true
rtspTransports: [tcp]
rtspAddress: 127.0.0.1:{RTSP_PORT}
rtmp: true
rtmpAddress: :{RTMP_PORT}
authMethod: internal
authInternalUsers:
  - user: any
    pass:
    ips: []
    permissions:
      - action: publish
        path:
  - user: any
    pass:
    ips: ["127.0.0.1", "::1"]
    permissions:
      - action: read
        path:
      - action: api
pathDefaults:
  source: publisher
paths:
  all_others:
"""


def start() -> bool:
    """Starts MediaMTX and the stream watcher. Returns False (ingest off) when it can't."""
    global _proc, _running
    if not ENABLED:
        logger.info("[ingest] disabled (INGEST_ENABLED=false)")
        return False
    if _api_alive():
        # Left running by an API process that was killed before it could stop
        # it. Its settings are ours (it answers on our localhost API port), so
        # use it rather than failing on the port it holds.
        _running = True
        _stop.clear()
        threading.Thread(target=_watch, name="drone-ingest", daemon=True).start()
        logger.info(f"[ingest] reusing the MediaMTX already running on port {RTMP_PORT}")
        return True
    binary = binary_path()
    if not binary.is_file():
        logger.warning(f"[ingest] MediaMTX not found at {binary} - always-on drone ingest is off (see README)")
        return False
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    config = DATA_DIR / "mediamtx.yml"
    config.write_text(_config(), encoding="utf-8")
    try:
        _proc = subprocess.Popen(
            [str(binary), str(config)],
            stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except OSError as exc:
        logger.error(f"[ingest] could not start MediaMTX: {exc}")
        return False
    # MediaMTX exits at once if a port is taken; give it a moment to say so.
    time.sleep(0.8)
    if _proc.poll() is not None:
        err = (_proc.stderr.read() if _proc.stderr else b"").decode(errors="replace").strip()
        logger.error(f"[ingest] MediaMTX exited: {err[-300:] or 'no output'} - is port {RTMP_PORT} in use?")
        _proc = None
        return False
    _running = True
    _stop.clear()
    threading.Thread(target=_watch, name="drone-ingest", daemon=True).start()
    logger.info(f"[ingest] listening for drones on rtmp://<this computer>:{RTMP_PORT}/{APP}/<name>")
    return True


def stop() -> None:
    global _proc, _running
    _running = False
    _stop.set()
    if _proc is not None:
        try:
            _proc.terminate()
            _proc.wait(timeout=5)
        except Exception:  # noqa: BLE001 - shutting down regardless
            pass
        _proc = None


def _get(endpoint: str) -> list[dict]:
    url = f"http://127.0.0.1:{API_PORT}{endpoint}?itemsPerPage=100"
    with urllib.request.urlopen(url, timeout=2) as res:
        return json.loads(res.read()).get("items", [])


def _ready_paths() -> dict[str, dict]:
    """
    Streams a drone is publishing, by path.

    MediaMTX marks a path ready about two seconds after the drone connects,
    once it has inspected the incoming tracks; until then the connection has
    no path, so there is nothing earlier to react to. Polling every POLL_S
    keeps our own share of the delay small.
    """
    return {item["name"]: item for item in _get("/v3/paths/list") if item.get("ready")}


def _label(path: str) -> str:
    name = path.split("/", 1)[-1]
    return name.replace("-", " ").replace("_", " ").title()


def _watch() -> None:
    while not _stop.is_set():
        try:
            sync(_ready_paths())
        except (urllib.error.URLError, OSError, ValueError) as exc:
            logger.debug(f"[ingest] MediaMTX API unreachable: {exc}")
        _stop.wait(POLL_S)


def sync(ready: dict[str, dict], now: float | None = None) -> None:
    """
    Opens a feed for each newly live stream and closes feeds whose stream has
    been gone for GRACE_S. Separate from the polling loop so it can be tested.
    """
    now = time.monotonic() if now is None else now
    with _state_lock:
        # Feeds an operator closed by hand: forget them so they are re-opened
        # next time, but only once that stream has actually stopped.
        live_ids = {f.id for f in registry.list_feeds()}
        for path, feed_id in list(_feed_for_path.items()):
            if feed_id not in live_ids:
                del _feed_for_path[path]
                if path in ready:
                    _dismissed.add(path)
        _dismissed.intersection_update(ready.keys())

        for path in ready:
            _last_seen[path] = now
            if path in _feed_for_path or path in _dismissed:
                continue
            source = f"rtsp://127.0.0.1:{RTSP_PORT}/{path}"
            try:
                feed = registry.add_feed(source=source, label=_label(path), kind="live", ingest_path=path)
            except registry.FeedLimitReached:
                logger.warning(f"[ingest] {path} is live but all {registry.MAX_FEEDS} feed slots are full")
                continue
            _feed_for_path[path] = feed.id
            logger.info(f"[ingest] {path} went live -> {feed.id}")

        for path, feed_id in list(_feed_for_path.items()):
            if path in ready or now - _last_seen.get(path, now) < GRACE_S:
                continue
            del _feed_for_path[path]
            _last_seen.pop(path, None)
            try:
                registry.remove_feed(feed_id)
            except registry.FeedNotFound:
                pass
            _drop_detection_state(feed_id)
            logger.info(f"[ingest] {path} stopped streaming -> closed {feed_id}")


def _drop_detection_state(feed_id: str) -> None:
    try:
        from routers.detect import drop_stream
        drop_stream(feed_id)
    except Exception:  # noqa: BLE001 - detection state is best-effort cleanup
        pass


def status() -> dict:
    """What Connect Drone shows: is ingest on, and which drones are live right now."""
    with _state_lock:
        live = dict(_feed_for_path)
    return {"enabled": is_running(), "port": RTMP_PORT, "app": APP, "live": live}


def reset() -> None:
    """Test hook."""
    with _state_lock:
        _feed_for_path.clear()
        _last_seen.clear()
        _dismissed.clear()
