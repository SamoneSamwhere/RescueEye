"""
RescueEye — media library for recorded drone footage.

Command Staff upload recorded clips; this module owns where the bytes live and
what is known about them. Files land in data/media/, captured stills in
data/media/frames/, and the metadata index is a single JSON file beside them.

A JSON index (rather than a database) keeps this consistent with the rest of
the service — detections live in an in-memory deque, inference history in a
JSONL log — and means an upload survives a restart without requiring the
Postgres/Prisma layer, which the API does not talk to.

Writes are serialised through a lock and the index is replaced atomically, so a
crash mid-write leaves the previous index intact rather than a truncated file.
"""
from __future__ import annotations

import json
import logging
import os
import re
import shutil
import subprocess
import threading
import time
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, BinaryIO, Callable

logger = logging.getLogger("rescueeye.media")

REPO_ROOT = Path(__file__).parent.parent
MEDIA_DIR = REPO_ROOT / "data" / "media"
FRAMES_DIR = MEDIA_DIR / "frames"
INDEX_FILE = MEDIA_DIR / "index.json"

ALLOWED_VIDEO_EXTS = {".mp4", ".mov", ".avi", ".mkv", ".ts", ".webm", ".m4v"}

# Mirrors the frontend MediaSourceType union.
SOURCE_UPLOADED = "UPLOADED_VIDEO"
SOURCE_LIVE = "LIVE_FEED"

_lock = threading.Lock()

# Anything outside this set is stripped from a caller-supplied filename before
# it is used on disk, so an upload cannot escape MEDIA_DIR or collide with the
# index file.
_SAFE_NAME = re.compile(r"[^A-Za-z0-9._-]+")


class MediaNotFound(Exception):
    pass


class UnsupportedMedia(Exception):
    pass


class MediaInUse(Exception):
    """The clip's file is still held open by another process."""
    pass


@dataclass
class CapturedFrame:
    """A still pulled out of a stored clip and kept for later review."""
    id: str
    media_id: str
    t_sec: float
    file: str
    captured_at: str
    note: str = ""


@dataclass
class MediaRecord:
    id: str
    original_name: str
    file: str                      # basename inside MEDIA_DIR
    size_bytes: int
    content_type: str
    source_type: str
    captured_at: str
    uploaded_at: str
    agency_id: str | None = None
    drone_id: str | None = None
    uploaded_by: str | None = None
    uploaded_by_name: str | None = None
    duration_sec: float | None = None
    width: int | None = None
    height: int | None = None
    note: str = ""
    frames: list[CapturedFrame] = field(default_factory=list)
    # The incident this footage was filmed at, and where the footage itself
    # says it was filmed (services/video_location.py VideoGeo, as a dict).
    incident_id: str | None = None
    geo: dict | None = None

    def to_dict(self) -> dict:
        d = asdict(self)
        d["frame_count"] = len(self.frames)
        return d


# ── Index persistence ─────────────────────────────────────────────────────────

def _ensure_dirs() -> None:
    MEDIA_DIR.mkdir(parents=True, exist_ok=True)
    FRAMES_DIR.mkdir(parents=True, exist_ok=True)


def _read_index() -> list[MediaRecord]:
    if not INDEX_FILE.exists():
        return []
    try:
        raw = json.loads(INDEX_FILE.read_text(encoding="utf-8"))
    except Exception as exc:
        # A corrupt index must not take the whole API down on startup; an empty
        # library is recoverable, a crash loop is not.
        logger.warning(f"[media] index unreadable ({exc}) — starting from empty")
        return []
    out: list[MediaRecord] = []
    for item in raw:
        frames = [CapturedFrame(**f) for f in item.pop("frames", [])]
        item.pop("frame_count", None)      # derived on write, never stored
        out.append(MediaRecord(**item, frames=frames))
    return out


def _write_index(records: list[MediaRecord]) -> None:
    _ensure_dirs()
    payload = []
    for r in records:
        d = asdict(r)
        d.pop("frame_count", None)
        payload.append(d)
    tmp = INDEX_FILE.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    os.replace(tmp, INDEX_FILE)            # atomic on POSIX and Windows


# ── Probing ───────────────────────────────────────────────────────────────────

def _probe(path: Path) -> tuple[float | None, int | None, int | None]:
    """(duration_sec, width, height) via ffprobe; all None when it can't be read."""
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "v:0",
             "-show_entries", "stream=width,height:format=duration",
             "-of", "json", str(path)],
            capture_output=True, text=True, timeout=60,
        ).stdout
        data = json.loads(out or "{}")
        stream = (data.get("streams") or [{}])[0]
        dur = data.get("format", {}).get("duration")
        return (
            round(float(dur), 2) if dur else None,
            int(stream["width"]) if stream.get("width") else None,
            int(stream["height"]) if stream.get("height") else None,
        )
    except Exception as exc:
        logger.warning(f"[media] ffprobe failed for {path.name}: {exc}")
        return None, None, None


def safe_name(name: str) -> str:
    """Filesystem-safe basename; never empty, never a path."""
    base = Path(name or "").name
    cleaned = _SAFE_NAME.sub("_", base).strip("._") or "upload"
    return cleaned[:120]


def _extract_frame(video: Path, t_sec: float, dest: Path) -> bool:
    try:
        subprocess.run(
            ["ffmpeg", "-loglevel", "error", "-ss", str(max(t_sec, 0)),
             "-i", str(video), "-frames:v", "1", "-q:v", "3", "-y", str(dest)],
            capture_output=True, timeout=120, check=True,
        )
        return dest.exists() and dest.stat().st_size > 0
    except Exception as exc:
        logger.warning(f"[media] frame extract failed at {t_sec}s: {exc}")
        return False


# ── Public API ────────────────────────────────────────────────────────────────

def save_upload(fileobj: BinaryIO, original_name: str, *,
                content_type: str = "video/mp4",
                agency_id: str | None = None,
                drone_id: str | None = None,
                uploaded_by: str | None = None,
                uploaded_by_name: str | None = None,
                source_type: str = SOURCE_UPLOADED,
                note: str = "",
                incident_id: str | None = None,
                locate: Callable[[Path], dict | None] | None = None) -> MediaRecord:
    """
    Persist an uploaded clip and register it in the library.

    `locate` reads where the stored file was filmed and may refuse it by
    raising UnsupportedMedia; the file is then removed and never indexed.
    """
    ext = Path(original_name or "").suffix.lower()
    if ext not in ALLOWED_VIDEO_EXTS:
        raise UnsupportedMedia(
            f"Unsupported file type '{ext or 'unknown'}'. "
            f"Allowed: {', '.join(sorted(ALLOWED_VIDEO_EXTS))}"
        )

    _ensure_dirs()
    media_id = uuid.uuid4().hex[:12]
    stored = f"{media_id}_{safe_name(original_name)}"
    dest = MEDIA_DIR / stored

    with dest.open("wb") as out:
        shutil.copyfileobj(fileobj, out)

    size = dest.stat().st_size
    if size == 0:
        dest.unlink(missing_ok=True)
        raise UnsupportedMedia("Uploaded file is empty.")

    geo = None
    if locate is not None:
        try:
            geo = locate(dest)
        except Exception:
            dest.unlink(missing_ok=True)
            raise

    duration, width, height = _probe(dest)
    now = datetime.now(timezone.utc).isoformat()
    record = MediaRecord(
        id=media_id,
        original_name=Path(original_name).name,
        file=stored,
        size_bytes=size,
        content_type=content_type or "video/mp4",
        source_type=source_type,
        captured_at=now,
        uploaded_at=now,
        agency_id=agency_id,
        drone_id=drone_id,
        uploaded_by=uploaded_by,
        uploaded_by_name=uploaded_by_name,
        duration_sec=duration,
        width=width,
        height=height,
        note=note,
        incident_id=incident_id,
        geo=geo,
    )

    with _lock:
        records = _read_index()
        records.append(record)
        _write_index(records)

    logger.info(f"[media] stored {stored} ({size // 1024} KB, {duration or '?'}s)")
    return record


def list_media(agency_id: str | None = None,
               source_type: str | None = None) -> list[MediaRecord]:
    """Newest first, optionally scoped to one agency."""
    with _lock:
        records = _read_index()
    if agency_id:
        records = [r for r in records if r.agency_id == agency_id]
    if source_type:
        records = [r for r in records if r.source_type == source_type]
    return sorted(records, key=lambda r: r.uploaded_at, reverse=True)


def get_media(media_id: str) -> MediaRecord:
    with _lock:
        for r in _read_index():
            if r.id == media_id:
                return r
    raise MediaNotFound(f"No media '{media_id}'")


def media_path(media_id: str) -> Path:
    """On-disk path of the stored clip, verified to exist."""
    rec = get_media(media_id)
    path = MEDIA_DIR / rec.file
    if not path.exists():
        raise MediaNotFound(f"File for '{media_id}' is missing from disk")
    return path


def frame_path(media_id: str, frame_id: str) -> Path:
    rec = get_media(media_id)
    for f in rec.frames:
        if f.id == frame_id:
            path = FRAMES_DIR / f.file
            if not path.exists():
                raise MediaNotFound(f"Frame file for '{frame_id}' is missing")
            return path
    raise MediaNotFound(f"No frame '{frame_id}' on media '{media_id}'")


def capture_frame(media_id: str, t_sec: float = 0.0, note: str = "") -> CapturedFrame:
    """Pull a still out of a stored clip and keep it alongside the library."""
    video = media_path(media_id)
    _ensure_dirs()
    frame_id = uuid.uuid4().hex[:12]
    name = f"{media_id}_{frame_id}.jpg"
    if not _extract_frame(video, t_sec, FRAMES_DIR / name):
        raise UnsupportedMedia(f"Could not extract a frame at {t_sec}s")

    frame = CapturedFrame(
        id=frame_id,
        media_id=media_id,
        t_sec=round(float(t_sec), 2),
        file=name,
        captured_at=datetime.now(timezone.utc).isoformat(),
        note=note,
    )
    with _lock:
        records = _read_index()
        for r in records:
            if r.id == media_id:
                r.frames.append(frame)
                break
        else:
            raise MediaNotFound(f"No media '{media_id}'")
        _write_index(records)

    logger.info(f"[media] captured frame {name} at {t_sec}s")
    return frame


def thumbnail_path(media_id: str) -> Path:
    """Poster frame for a clip, generated on first request and cached."""
    video = media_path(media_id)
    _ensure_dirs()
    dest = FRAMES_DIR / f"{media_id}_thumb.jpg"
    if dest.exists() and dest.stat().st_size > 0:
        return dest
    rec = get_media(media_id)
    # A frame one second in is far more likely to carry content than frame 0,
    # which is often black on drone footage.
    at = 1.0 if (rec.duration_sec or 0) > 2 else 0.0
    if not _extract_frame(video, at, dest):
        raise UnsupportedMedia("Could not generate a thumbnail")
    return dest


def _unlink_with_retry(path: Path, attempts: int = 20, delay: float = 0.1) -> bool:
    """
    Delete a file, tolerating a brief lock held by a process that is exiting.

    A feed playing this clip is closed before deletion, but `terminate()` only
    signals FFmpeg — on Windows the handle survives for a few more milliseconds
    and `unlink` raises PermissionError (WinError 32). Retrying briefly is far
    simpler than making every caller wait on the process.
    """
    for attempt in range(attempts):
        try:
            path.unlink(missing_ok=True)
            return True
        except PermissionError:
            if attempt == attempts - 1:
                logger.warning(f"[media] {path.name} still locked after {attempts} attempts")
                return False
            time.sleep(delay)
    return False


def delete_media(media_id: str) -> None:
    """Remove a clip, its captured frames, and its index entry."""
    with _lock:
        records = _read_index()
        keep = [r for r in records if r.id != media_id]
        if len(keep) == len(records):
            raise MediaNotFound(f"No media '{media_id}'")
        gone = next(r for r in records if r.id == media_id)

    # Release the bytes before dropping the index entry, so a file that cannot
    # be deleted doesn't become an orphan with nothing pointing at it.
    removed = _unlink_with_retry(MEDIA_DIR / gone.file)
    for f in gone.frames:
        _unlink_with_retry(FRAMES_DIR / f.file)
    _unlink_with_retry(FRAMES_DIR / f"{media_id}_thumb.jpg")

    if not removed:
        raise MediaInUse(
            f"'{gone.original_name}' is still being read by another process. "
            "Stop the feed playing it and try again."
        )

    with _lock:
        _write_index([r for r in _read_index() if r.id != media_id])
    logger.info(f"[media] deleted {gone.file} and {len(gone.frames)} frame(s)")


def stats() -> dict:
    records = list_media()
    return {
        "count":       len(records),
        "frame_count": sum(len(r.frames) for r in records),
        "bytes":       sum(r.size_bytes for r in records),
        "dir":         str(MEDIA_DIR),
    }
