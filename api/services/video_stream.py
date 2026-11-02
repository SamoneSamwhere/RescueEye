"""
H.264 copy of a feed for the browser's live view.

The MJPEG view sends every frame as a whole JPEG. Through the Cloudflare tunnel
that capped the view at 15 fps (~9 Mbit/s per viewer at 960 px); 30 fps would
need ~18. Video only sends what changed between frames: the same 960 px at
30 fps measures ~2.5 Mbit/s.

One FFmpeg encoder per feed, started by the first viewer and stopped shortly
after the last one leaves. It encodes the frames the AI already reads (the
drone's RTMP listener accepts a single connection, so the source cannot be
opened twice) and its output is split into frames and fanned out to every
viewer's WebSocket. Detection is untouched: it keeps reading full frames.

Wire format, one WebSocket message per frame:
    byte 0      1 for a keyframe, else 0
    bytes 1-8   server send time, ms (float64, little-endian)
    bytes 9-    the frame's H.264 NAL units, Annex B
The time lets the browser undo network bursts before showing the frame.
"""
from __future__ import annotations

import asyncio
import logging
import os
import struct
import subprocess
import threading
import time

from services import feed_registry as registry

logger = logging.getLogger("rescueeye.video")

VIDEO_MAX_WIDTH = int(os.getenv("VIDEO_MAX_WIDTH", "960"))
VIDEO_BITRATE_K = int(os.getenv("VIDEO_BITRATE_K", "2500"))
# One keyframe a second: how long a new viewer waits at most, and how long a
# viewer whose connection fell behind waits to resume.
VIDEO_GOP = int(os.getenv("VIDEO_GOP", "30"))
# A viewer more than this many frames behind is skipped ahead to the next
# keyframe instead of being fed an ever-older backlog.
MAX_QUEUED_FRAMES = 45
# Keep the encoder this long after the last viewer leaves: a page reload or a
# panel remount reconnects within it and gets the picture at once.
IDLE_STOP_S = 10.0

_AUD = b"\x00\x00\x00\x01\x09"


def encoder_cmd(fps: float) -> list[str]:
    """FFmpeg reading JPEG frames on stdin and writing H.264 to stdout."""
    return [
        registry._ffmpeg_binary(), "-loglevel", "error",
        "-f", "image2pipe", "-c:v", "mjpeg", "-framerate", str(fps), "-i", "pipe:0",
        "-an", "-vf", f"scale=trunc(min({VIDEO_MAX_WIDTH}\\,iw)/2)*2:-2",
        # ultrafast + zerolatency: no lookahead, no B-frames, so each frame
        # leaves the encoder as soon as it arrives. Baseline profile decodes
        # everywhere WebCodecs does.
        "-c:v", "libx264", "-preset", "ultrafast", "-tune", "zerolatency",
        "-profile:v", "baseline", "-pix_fmt", "yuv420p",
        "-g", str(VIDEO_GOP), "-bf", "0",
        "-b:v", f"{VIDEO_BITRATE_K}k", "-maxrate", f"{VIDEO_BITRATE_K}k",
        "-bufsize", f"{VIDEO_BITRATE_K // 2}k",
        # aud: an access-unit delimiter before every frame, which is what the
        # reader splits on. repeat-headers: SPS/PPS before every keyframe, so a
        # viewer can start at any keyframe.
        "-x264-params", "aud=1:repeat-headers=1",
        "-f", "h264", "pipe:1",
    ]


def split_frames(buf: bytes) -> tuple[list[bytes], bytes]:
    """Complete frames in `buf` (each starts at an AUD), and the unfinished rest."""
    starts = []
    i = buf.find(_AUD)
    while i != -1:
        starts.append(i)
        i = buf.find(_AUD, i + len(_AUD))
    if len(starts) < 2:
        return [], buf
    frames = [buf[a:b] for a, b in zip(starts, starts[1:])]
    return frames, buf[starts[-1]:]


def is_keyframe(frame: bytes) -> bool:
    """Whether the frame holds an IDR slice (NAL type 5)."""
    i = frame.find(b"\x00\x00\x01")
    while i != -1:
        if i + 3 < len(frame) and frame[i + 3] & 0x1F == 5:
            return True
        i = frame.find(b"\x00\x00\x01", i + 3)
    return False


def pack(frame: bytes, key: bool, sent_ms: float) -> bytes:
    return struct.pack("<Bd", 1 if key else 0, sent_ms) + frame


class _Viewer:
    def __init__(self, loop: asyncio.AbstractEventLoop):
        self.loop = loop
        self.queue: asyncio.Queue[bytes] = asyncio.Queue()
        self.need_key = True

    def offer(self, packed: bytes, key: bool) -> None:
        """Called on the encoder thread; hands the frame to the viewer's loop."""
        self.loop.call_soon_threadsafe(self._offer, packed, key)

    def _offer(self, packed: bytes, key: bool) -> None:
        if self.queue.qsize() >= MAX_QUEUED_FRAMES:
            # Behind by over a second: drop the backlog and resume at the next
            # keyframe (a P-frame without its predecessors cannot be decoded).
            while not self.queue.empty():
                self.queue.get_nowait()
            self.need_key = True
        if self.need_key:
            if not key:
                return
            self.need_key = False
        self.queue.put_nowait(packed)


class FeedVideo:
    """The encoder and viewers of one feed."""

    def __init__(self, feed: registry.Feed):
        self.feed = feed
        self.viewers: set[_Viewer] = set()
        self.lock = threading.Lock()
        self.proc: subprocess.Popen | None = None
        self.idle_since: float | None = None
        # The frames since the last keyframe, so a new viewer starts at once
        # rather than waiting up to a GOP for the next one.
        self.gop: list[bytes] = []

    # ── viewers ──
    def join(self, loop: asyncio.AbstractEventLoop) -> _Viewer:
        viewer = _Viewer(loop)
        with self.lock:
            for packed in self.gop:
                viewer._offer(packed, packed[0] == 1)
            self.viewers.add(viewer)
            self.idle_since = None
            if self.proc is None or self.proc.poll() is not None:
                self._start()
        return viewer

    def leave(self, viewer: _Viewer) -> None:
        with self.lock:
            self.viewers.discard(viewer)
            if not self.viewers:
                self.idle_since = time.monotonic()

    # ── encoder ──
    def _start(self) -> None:
        fps = float(os.getenv("FRAME_RATE", "8"))
        cmd = encoder_cmd(fps)
        logger.info(f"[video:{self.feed.id}] encoder: {' '.join(cmd)}")
        self.proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                     stderr=subprocess.DEVNULL, bufsize=0)
        self.gop = []
        proc = self.proc
        threading.Thread(target=self._write, args=(proc,), daemon=True).start()
        threading.Thread(target=self._read, args=(proc,), daemon=True).start()

    def _should_stop(self) -> bool:
        if self.feed.stop_event.is_set():
            return True
        with self.lock:
            return self.idle_since is not None and time.monotonic() - self.idle_since > IDLE_STOP_S

    def _write(self, proc: subprocess.Popen) -> None:
        """Feed every new frame of the feed to the encoder."""
        last_seq = self.feed.seq
        try:
            while proc.poll() is None and not self._should_stop():
                frame, seq = self.feed.wait_for_frame(last_seq, timeout=0.5)
                if frame is None or seq == last_seq:
                    continue
                last_seq = seq
                proc.stdin.write(frame)
        except (BrokenPipeError, OSError, ValueError):
            pass
        finally:
            try:
                proc.stdin.close()
            except OSError:
                pass
            # stdin closed lets FFmpeg flush and exit; make sure it does.
            try:
                proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                proc.kill()
            logger.info(f"[video:{self.feed.id}] encoder stopped")
            with self.lock:
                if self.proc is proc:
                    self.proc = None
                # A viewer that joined while this encoder was shutting down, or
                # an encoder that crashed under its viewers: start a fresh one.
                restart = bool(self.viewers) and not self.feed.stop_event.is_set()
                if restart:
                    self.idle_since = None
            if restart:
                time.sleep(0.5)
                with self.lock:
                    if self.viewers and self.proc is None:
                        self._start()
            else:
                _forget_if_idle(self)

    def _read(self, proc: subprocess.Popen) -> None:
        """Split the encoder's output into frames and send them to the viewers."""
        buf = b""
        while True:
            chunk = proc.stdout.read(65536)
            if not chunk:
                return
            frames, buf = split_frames(buf + chunk)
            for frame in frames:
                key = is_keyframe(frame)
                packed = pack(frame, key, time.time() * 1000)
                with self.lock:
                    if key:
                        self.gop = []
                    self.gop.append(packed)
                    viewers = list(self.viewers)
                for viewer in viewers:
                    viewer.offer(packed, key)


_videos: dict[str, FeedVideo] = {}
_videos_lock = threading.Lock()


def for_feed(feed: registry.Feed) -> FeedVideo:
    with _videos_lock:
        video = _videos.get(feed.id)
        if video is None or video.feed is not feed:
            video = _videos[feed.id] = FeedVideo(feed)
        return video


def _forget_if_idle(video: FeedVideo) -> None:
    with _videos_lock, video.lock:
        if not video.viewers and _videos.get(video.feed.id) is video:
            _videos.pop(video.feed.id, None)
