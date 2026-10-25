"""
Multi-feed registry.

The platform originally carried a single drone feed held in module-level
globals, where uploading a video or setting a live URL *replaced* it. An
operator watching one aircraft is not a command centre, so feeds are now
independent entries in a registry: each owns its own FFmpeg process, frame
buffer and lock, and can be added or removed without disturbing the others.

Capped at MAX_FEEDS because each feed is a live FFmpeg transcode plus a
detection loop in the browser — beyond four, a laptop running YOLO alongside
them starts dropping frames, which is worse than refusing the fifth.
"""
import functools
import io
import logging
import os
import subprocess
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

from PIL import Image

logger = logging.getLogger("rescueeye.feeds")

MAX_FEEDS = 4

# Detection runs on every feed, so the per-feed cadence is stretched as feeds
# are added to keep total inference load roughly constant. The browser reads
# `suggestedDetectIntervalMs` from the feed list rather than hardcoding it.
BASE_DETECT_INTERVAL_MS = 350
MAX_DETECT_INTERVAL_MS = 1500


def _ffmpeg_binary() -> str:
    """
    Which FFmpeg to run.

    A bare "ffmpeg" takes whatever is first on PATH, and that is routinely an
    ancient build — the box this was written on resolved to a 2013 snapshot,
    which plays a local MP4 happily but cannot decode H.265 and does not
    understand the current RTSP timeout flag. Both only bite once a real
    aircraft is connected, which is the worst moment to discover them.

    imageio-ffmpeg is already a dependency (frame extraction) and ships a
    modern static build, so prefer that over PATH roulette. FFMPEG_BINARY
    overrides everything for a deployment that pins its own.
    """
    override = os.getenv("FFMPEG_BINARY", "").strip()
    if override:
        return override
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        logger.warning("[feed] imageio-ffmpeg unavailable — falling back to 'ffmpeg' on PATH")
        return "ffmpeg"


def _is_network_source(source: str) -> bool:
    return source.startswith(("rtsp://", "rtsps://", "rtmp://", "udp://", "http://", "https://"))


def _is_listen_source(source: str) -> bool:
    """
    True when we must *receive* the stream rather than fetch it.

    Consumer drones (DJI in particular) run no server of their own: the phone
    app pushes RTMP outward to an address you give it. Binding the host to a
    wildcard is how an operator says "the aircraft will call us" — FFmpeg then
    serves the endpoint itself, so no separate relay has to be installed.
    """
    return source.startswith(("rtmp://0.0.0.0", "rtmp://:", "rtmp://*"))


def _normalise_listen_source(source: str) -> str:
    """FFmpeg wants a concrete bind address; 'rtmp://:1935/x' is shorthand."""
    return source.replace("rtmp://*", "rtmp://0.0.0.0", 1).replace("rtmp://:", "rtmp://0.0.0.0:", 1)


# Frames wider than this are scaled down by FFmpeg before they ever reach the
# buffer. 4K frames cost roughly 3x as much to decode and process per detection
# pass while measuring identical detection accuracy, and the MJPEG view is
# downscaled to 1280x720 for the browser anyway — so the extra pixels are paid
# for on every frame and used by nothing. Raise it if a source needs the detail.
FEED_MAX_WIDTH = int(os.getenv("FEED_MAX_WIDTH", "1920"))


@functools.lru_cache(maxsize=1)
def _rtsp_timeout_flag() -> str:
    """
    The RTSP socket-timeout option this FFmpeg understands.

    FFmpeg before 5.0 calls it -stimeout, and reads -timeout as "listen for an
    incoming connection" - so on the 4.2 build imageio-ffmpeg ships, every RTSP
    source failed at once with "Unable to open RTSP for listening". 5.0+
    renamed it to -timeout and dropped -stimeout.
    """
    try:
        out = subprocess.run([_ffmpeg_binary(), "-hide_banner", "-h", "demuxer=rtsp"],
                             capture_output=True, text=True, timeout=10).stdout
    except (OSError, subprocess.SubprocessError):
        return "-timeout"
    return "-stimeout" if "-stimeout" in out else "-timeout"


def _build_ffmpeg_cmd(source: str, fps: float) -> list[str]:
    """FFmpeg command with source-appropriate flags."""
    cmd = [_ffmpeg_binary(), "-loglevel", "error"]
    if source.startswith(("rtsp://", "rtsps://")):
        cmd += ["-rtsp_transport", "tcp", _rtsp_timeout_flag(), "5000000"]
    if _is_network_source(source):
        # Live sources are latency-critical: FFmpeg's defaults spend up to five
        # seconds probing the stream before emitting anything, then keep a
        # reorder buffer that adds more. A drone feed is a single H.264 track
        # with nothing to discover, so probing is pure delay — and an operator
        # watching a casualty needs the current frame, not a smooth one.
        cmd += ["-fflags", "nobuffer", "-flags", "low_delay",
                "-probesize", "32", "-analyzeduration", "0"]
    if _is_listen_source(source):
        # Wait for the aircraft to publish. No -timeout: the gap between
        # arming the feed and the pilot hitting "Go Live" is measured in
        # minutes, and a listener that gave up would strand the operator.
        source = _normalise_listen_source(source)
        cmd += ["-listen", "1"]
    if not _is_network_source(source):
        # -re paces file playback to real time; omit for live network sources.
        # -stream_loop loops inside the one process: the producer used to reach
        # EOF, tear FFmpeg down and start it again, which froze a demo clip for
        # about a second every time it wrapped. Looping here makes the seam
        # invisible and leaves the restart path for genuine failures.
        cmd += ["-stream_loop", "-1", "-re"]
    # -1 derives the height from the aspect ratio. (-2, which would also force
    # an even height, is rejected by some FFmpeg builds with "Size values less
    # than -1 are not acceptable".) min() leaves a source already narrower than
    # the cap untouched rather than upscaling it.
    vf = f"fps={fps},scale='min({FEED_MAX_WIDTH},iw)':-1"
    # JPEG quality of the frames FFmpeg hands us (2 = best, 31 = worst). These
    # frames are now served to the browser as-is rather than re-encoded, so the
    # setting decides bytes on the wire as well as encode cost. q3 is visually
    # lossless and roughly 2.5x the size of q6 for no benefit anyone can see at
    # 720p, and that extra bandwidth was costing delivered frames.
    quality = os.getenv("FEED_JPEG_QUALITY", "6")
    cmd += ["-i", source, "-vf", vf, "-f", "image2pipe",
            "-vcodec", "mjpeg", "-q:v", quality, "pipe:1"]
    return cmd


def _downscale_jpeg(jpeg: bytes, w: int = 1280, h: int = 720) -> bytes:
    """
    Fit a frame inside w x h for the browser, re-encoding only if it must.

    The old version decoded and re-encoded unconditionally. When the producer
    already emits frames at or below the display size that is a full JPEG
    decode plus encode per frame per viewer, spent to produce a picture the
    same size as the input and slightly worse, because re-encoding is lossy.
    Reading the header is enough to find that out, and Image.open does not
    decode pixels until they are asked for.

    The fit also preserves aspect ratio now; the fixed resize stretched any
    source that was not exactly 16:9.
    """
    src = Image.open(io.BytesIO(jpeg))
    if src.width <= w and src.height <= h:
        return jpeg                      # already small enough - hand it back untouched
    scale = min(w / src.width, h / src.height)
    size = (max(1, round(src.width * scale)), max(1, round(src.height * scale)))
    buf = io.BytesIO()
    src.resize(size, Image.BILINEAR).save(buf, format="JPEG", quality=78)
    return buf.getvalue()


@dataclass
class Feed:
    """One independently-running video source."""
    id: str
    label: str
    source: str
    kind: str                       # 'upload' | 'live' | 'synthetic'

    lock: threading.Lock = field(default_factory=threading.Lock)
    stop_event: threading.Event = field(default_factory=threading.Event)
    current_frame: bytes | None = None
    # Incremented on every decoded frame. Lets the MJPEG generator block until
    # there is genuinely something new instead of waking on a timer and
    # re-sending a frame the browser already has.
    seq: int = 0
    # Browser-sized copy of current_frame, built at most once per frame no
    # matter how many viewers are watching. Two panels on one feed used to pay
    # for the same conversion twice.
    display_frame: bytes | None = None
    frame_ready: threading.Condition = field(default_factory=threading.Condition)
    active: bool = False
    producer: str = "none"          # 'ffmpeg' | 'synthetic' | 'none'
    proc: subprocess.Popen | None = None
    created_at: float = field(default_factory=time.time)
    # Set for a feed opened automatically when a drone started publishing to
    # the always-on ingest server (services/drone_ingest.py), e.g. "live/drone1".
    ingest_path: str | None = None

    def snapshot(self) -> bytes | None:
        with self.lock:
            return self.current_frame

    def publish(self, frame: bytes) -> None:
        """Store a newly decoded frame and wake anyone waiting on it."""
        with self.lock:
            self.current_frame = frame
            self.seq += 1
            self.display_frame = None      # invalidate the browser-sized copy
        with self.frame_ready:
            self.frame_ready.notify_all()

    def display_jpeg(self) -> bytes | None:
        """Current frame at browser size, converted once and reused."""
        with self.lock:
            if self.display_frame is not None:
                return self.display_frame
            raw = self.current_frame
        if raw is None:
            return None
        try:
            shown = _downscale_jpeg(raw)
        except Exception:
            shown = raw
        with self.lock:
            self.display_frame = shown
        return shown

    def wait_for_frame(self, last_seq: int, timeout: float = 1.0) -> tuple[bytes | None, int]:
        """Block until a frame newer than `last_seq` exists, or time out."""
        with self.frame_ready:
            if self.seq <= last_seq:
                self.frame_ready.wait(timeout)
        with self.lock:
            return self.current_frame, self.seq

    @property
    def drone_id(self) -> str | None:
        """
        Which drone this feed shows, for looking up its position
        (services/drone_locations.py): the stream name for an ingested drone
        ("live/alpha" -> "alpha"), else the feed's name. None for recordings.
        """
        if self.ingest_path:
            return self.ingest_path.split("/", 1)[-1]
        if self.kind != "live":
            return None
        from services.drone_ingest import slugify
        return slugify(self.label)

    def to_dict(self) -> dict:
        return {
            "id":        self.id,
            "label":     self.label,
            "kind":      self.kind,
            "source":    self.source,
            "active":    self.active,
            "producer":  self.producer,
            "hasFrame":  self.current_frame is not None,
            "createdAt": self.created_at,
            "ingestPath": self.ingest_path,
            "droneId":   self.drone_id,
        }


_registry: dict[str, Feed] = {}
_registry_lock = threading.Lock()
_counter = 0


class FeedLimitReached(Exception):
    """Raised when adding would exceed MAX_FEEDS."""


class FeedNotFound(Exception):
    pass


def detect_interval_ms() -> int:
    """
    Per-feed detection cadence. Every feed detects, so the interval widens with
    feed count to spread inference load rather than multiplying it.

    The base was 2500ms when a pass cost ~630ms and the overlay visibly lagged
    the video. A pass is now ~190ms, so the gap between updates — not inference
    — was what made the box trail the casualty. Clients run their cycles back to
    back, so this is a floor rather than a fixed period: it can never queue
    requests faster than the model clears them.
    """
    n = max(len(_registry), 1)
    return min(BASE_DETECT_INTERVAL_MS * n // 1, MAX_DETECT_INTERVAL_MS)


def _synthetic_producer(feed: Feed, fps: float):
    # Imported lazily: the synthetic frame painter lives with the router's
    # presentation helpers and pulls in PIL font handling.
    from routers.stream import synthetic_frame

    feed.active = True
    feed.producer = "synthetic"
    tick = 0
    interval = 1.0 / fps
    while not feed.stop_event.is_set():
        frame = synthetic_frame(tick, label=feed.label)
        feed.publish(frame)
        tick += 1
        time.sleep(interval)
    feed.active = False


def _ffmpeg_producer(feed: Feed, fps: float):
    cmd = _build_ffmpeg_cmd(feed.source, fps)
    logger.info(f"[feed:{feed.id}] FFmpeg: {' '.join(cmd)}")
    feed.producer = "ffmpeg"
    feed.active = True
    try:
        while not feed.stop_event.is_set():
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, bufsize=0)
            feed.proc = proc
            buf = b""
            while not feed.stop_event.is_set():
                chunk = proc.stdout.read(65536)
                if not chunk:
                    break
                buf += chunk
                while True:
                    s = buf.find(b"\xff\xd8")
                    e = buf.find(b"\xff\xd9", s + 2)
                    if s == -1 or e == -1:
                        break
                    feed.publish(buf[s:e + 2])
                    buf = buf[e + 2:]
            proc.wait()
            if feed.stop_event.is_set():
                break
            # Files reach EOF; loop them so a demo clip runs continuously.
            # A listening endpoint "ends" when the aircraft stops publishing,
            # and the same restart re-arms it for the next takeoff.
            if _is_listen_source(feed.source):
                logger.info(f"[feed:{feed.id}] publisher disconnected — waiting for next stream")
            else:
                logger.info(f"[feed:{feed.id}] source ended — restarting")
            time.sleep(0.5)
    except FileNotFoundError:
        logger.warning(f"[feed:{feed.id}] FFmpeg not installed — synthetic fallback")
        feed.stop_event.clear()
        _synthetic_producer(feed, fps)
    except Exception as exc:
        logger.error(f"[feed:{feed.id}] error: {exc}")
    finally:
        feed.active = False
        feed.proc = None


def _start_producer(feed: Feed) -> None:
    fps = float(os.getenv("FRAME_RATE", "8"))
    playable = feed.source and (_is_network_source(feed.source) or os.path.isfile(feed.source))
    target = _ffmpeg_producer if playable else _synthetic_producer
    if not playable and feed.source:
        logger.warning(f"[feed:{feed.id}] source '{feed.source}' unplayable — synthetic")
        feed.kind = "synthetic"
    threading.Thread(target=target, args=(feed, fps), daemon=True).start()


def add_feed(source: str, label: str | None = None, kind: str = "live",
             ingest_path: str | None = None) -> Feed:
    """
    Registers and starts a new feed.

    Raises FeedLimitReached rather than evicting an existing feed — a panel
    disappearing mid-demo is more confusing than being told to remove one.
    """
    global _counter
    with _registry_lock:
        if len(_registry) >= MAX_FEEDS:
            raise FeedLimitReached(
                f"Maximum of {MAX_FEEDS} feeds reached — remove one before adding another."
            )
        _counter += 1
        feed_id = f"feed{_counter}"
        # The source decides what a feed is, not the caller: a file on disk is
        # a recording however it was added. The startup feed and a file path
        # posted to /stream/feeds both arrived as "live", so a looping demo clip
        # was badged LIVE in front of an operator who would take it at its word.
        if not source:
            kind = "synthetic"
        elif not (_is_network_source(source) or _is_listen_source(source)):
            kind = "upload"
        feed = Feed(
            id=feed_id,
            label=label or f"Feed {_counter}",
            source=source,
            kind=kind,
            ingest_path=ingest_path,
        )
        _registry[feed_id] = feed

    _start_producer(feed)
    logger.info(f"[feed:{feed.id}] added ({feed.kind}) — {feed.source or 'synthetic'}")
    return feed


def remove_feed(feed_id: str) -> None:
    with _registry_lock:
        feed = _registry.pop(feed_id, None)
    if feed is None:
        raise FeedNotFound(feed_id)
    feed.stop_event.set()
    if feed.proc:
        try:
            feed.proc.terminate()
        except Exception:
            pass
    logger.info(f"[feed:{feed.id}] removed")


def get_feed(feed_id: str) -> Feed:
    feed = _registry.get(feed_id)
    if feed is None:
        raise FeedNotFound(feed_id)
    return feed


def list_feeds() -> list[Feed]:
    return sorted(_registry.values(), key=lambda f: f.created_at)


def primary_feed() -> Feed | None:
    """
    The oldest feed. Backs the legacy single-feed endpoints (/stream/feed3,
    /stream/status) that the mobile app and older docs still point at.
    """
    feeds = list_feeds()
    return feeds[0] if feeds else None


def count() -> int:
    return len(_registry)


def shutdown_all() -> None:
    for feed_id in list(_registry.keys()):
        try:
            remove_feed(feed_id)
        except FeedNotFound:
            pass
