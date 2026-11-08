"""
Where a recorded video was filmed, read from the file itself.

Two kinds of recording carry their position:

  * Phones (Android, iPhone) write one GPS point into the MP4 header when the
    camera has location on: an ISO 6709 string such as "+10.3385+123.9118/",
    under `location` or `com.apple.quicktime.location.ISO6709`.
  * DJI drones write a flight log as subtitles - one caption per frame with the
    aircraft's latitude, longitude and height. Many models embed it in the MP4
    as a subtitle track; with "Video Captions" switched on in DJI Fly the same
    log is saved beside the video as an .SRT file, which can be uploaded with it.

A drone track is kept as one point per second, so detections from a clip are
placed where the drone was at that moment of the video, not just where it took
off. Newer DJI models that only store the binary "djmd" stream are not read;
for those the .SRT file (Video Captions on) is the way in.
"""
from __future__ import annotations

import bisect
import json
import logging
import re
import subprocess
from dataclasses import asdict, dataclass, field
from pathlib import Path

logger = logging.getLogger("rescueeye.video_location")

# How far off each kind of position may be. A drone's GPS says where the
# aircraft is; what it films is up to ~50 m away from a typical survey height.
# A phone's header point is where the phone was when recording started.
ACCURACY_M = {"dji_srt": 30.0, "srt_file": 30.0, "iso6709": 20.0, "simulated": 0.0}

_ISO6709 = re.compile(r"([+-]\d{1,2}(?:\.\d+)?)([+-]\d{1,3}(?:\.\d+)?)([+-]\d+(?:\.\d+)?)?")
_SRT_TIME = re.compile(r"(\d+):(\d{2}):(\d{2})[,.](\d{1,3})\s*-->")
_LAT = re.compile(r"\[\s*latitude\s*:\s*(-?\d+(?:\.\d+)?)", re.I)
_LNG = re.compile(r"\[\s*long(?:i)?tude\s*:\s*(-?\d+(?:\.\d+)?)", re.I)
_REL_ALT = re.compile(r"rel_alt\s*:\s*(-?\d+(?:\.\d+)?)", re.I)
_ALT = re.compile(r"\[\s*altitude\s*:\s*(-?\d+(?:\.\d+)?)", re.I)
# Older DJI captions: "GPS (123.9118, 10.3385, 19) ... H 30.0m" - longitude first.
_GPS_TUPLE = re.compile(r"GPS\s*\(\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)", re.I)
_HEIGHT = re.compile(r"\bH\s*:?\s*(-?\d+(?:\.\d+)?)\s*m", re.I)


@dataclass
class VideoGeo:
    """A recording's position: one point, or a track through the clip."""
    lat: float
    lng: float
    source: str                     # 'video_metadata' | 'simulated'
    method: str                     # 'dji_srt' | 'srt_file' | 'iso6709' | 'simulated'
    accuracy_m: float
    # [t_sec, lat, lng, altitude_m | None], one per second; empty for a single point.
    track: list[list] = field(default_factory=list)

    def at(self, t_sec: float) -> tuple[float, float, float | None]:
        """Where the camera was `t_sec` into the clip."""
        if not self.track:
            return self.lat, self.lng, None
        i = bisect.bisect_right([p[0] for p in self.track], t_sec) - 1
        p = self.track[max(i, 0)]
        return p[1], p[2], p[3]

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict | None) -> "VideoGeo | None":
        return cls(**d) if d else None


def parse_iso6709(text: str) -> tuple[float, float] | None:
    m = _ISO6709.search(text or "")
    if not m:
        return None
    lat, lng = float(m.group(1)), float(m.group(2))
    return (lat, lng) if _plausible(lat, lng) else None


def _plausible(lat: float, lng: float) -> bool:
    # 0,0 is what a drone writes before it has a GPS fix.
    return -90 <= lat <= 90 and -180 <= lng <= 180 and not (abs(lat) < 1e-6 and abs(lng) < 1e-6)


def parse_srt(text: str) -> list[list]:
    """DJI flight captions -> [[t_sec, lat, lng, alt], ...], one point per second."""
    track: list[list] = []
    for block in re.split(r"\r?\n\s*\r?\n", text or ""):
        tm = _SRT_TIME.search(block)
        if not tm:
            continue
        h, m, s, ms = tm.groups()
        t = int(h) * 3600 + int(m) * 60 + int(s) + int(ms.ljust(3, "0")) / 1000
        lat_m, lng_m = _LAT.search(block), _LNG.search(block)
        if lat_m and lng_m:
            lat, lng = float(lat_m.group(1)), float(lng_m.group(1))
            alt_m = _REL_ALT.search(block) or _ALT.search(block)
        else:
            g = _GPS_TUPLE.search(block)
            if not g:
                continue
            lng, lat = float(g.group(1)), float(g.group(2))
            alt_m = _HEIGHT.search(block)
        if not _plausible(lat, lng):
            continue
        if track and t - track[-1][0] < 1.0:
            continue
        track.append([round(t, 2), round(lat, 7), round(lng, 7),
                      round(float(alt_m.group(1)), 1) if alt_m else None])
    return track


def _from_track(track: list[list], method: str) -> VideoGeo:
    return VideoGeo(lat=track[0][1], lng=track[0][2], source="video_metadata",
                    method=method, accuracy_m=ACCURACY_M[method], track=track)


def _ffprobe(path: Path) -> dict:
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries",
             "format_tags:stream=index,codec_type:stream_tags", "-of", "json", str(path)],
            capture_output=True, text=True, timeout=60, stdin=subprocess.DEVNULL,
        ).stdout
        return json.loads(out or "{}")
    except Exception as exc:
        logger.warning(f"[video-location] ffprobe failed for {path.name}: {exc}")
        return {}


def _embedded_captions(path: Path, stream_index: int) -> str:
    try:
        return subprocess.run(
            ["ffmpeg", "-nostdin", "-v", "error", "-i", str(path), "-map", f"0:{stream_index}", "-f", "srt", "-"],
            capture_output=True, text=True, timeout=120, encoding="utf-8", errors="replace",
            stdin=subprocess.DEVNULL,
        ).stdout
    except Exception as exc:
        logger.warning(f"[video-location] caption extract failed for {path.name}: {exc}")
        return ""


def read_location(video: Path, captions_text: str | None = None) -> VideoGeo | None:
    """
    The best position the recording carries, or None.

    A drone track beats a single header point: it follows the drone. An .SRT
    uploaded alongside wins over everything in the file, since someone chose
    to provide it.
    """
    if captions_text:
        track = parse_srt(captions_text)
        if track:
            return _from_track(track, "srt_file")

    info = _ffprobe(video)
    for stream in info.get("streams", []):
        if stream.get("codec_type") == "subtitle":
            track = parse_srt(_embedded_captions(video, int(stream["index"])))
            if track:
                return _from_track(track, "dji_srt")

    tags = {k.lower(): v for k, v in (info.get("format", {}).get("tags") or {}).items()}
    for stream in info.get("streams", []):
        for k, v in (stream.get("tags") or {}).items():
            tags.setdefault(k.lower(), v)
    for key in ("com.apple.quicktime.location.iso6709", "location", "location-eng"):
        point = parse_iso6709(tags.get(key, ""))
        if point:
            return VideoGeo(lat=point[0], lng=point[1], source="video_metadata",
                            method="iso6709", accuracy_m=ACCURACY_M["iso6709"])
    return None


def simulated_at(lat: float, lng: float) -> VideoGeo:
    """No position in the file: stand in the incident's, marked as simulated."""
    return VideoGeo(lat=lat, lng=lng, source="simulated", method="simulated", accuracy_m=0.0)
