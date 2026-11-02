"""
Casualty discrimination - deciding which detected *people* are casualties.

Both detectors in this system find people, not casualties. victim_best.onnx
declares exactly one class, "person", and the COCO assist pass is filtered to
COCO class 0. Until this module existed, routers/detect.py simply relabelled
every person box "casualty", so a bystander, a rescuer, or a crowd on a rooftop
all raised VICTIM_DETECTED and landed in the Command Staff review queue.

Nothing here detects anything. It takes person boxes and decides which of them
show evidence of being a casualty, using three signals that fail in different
conditions:

  posture    Prone, supine and collapsed bodies sit differently in frame from
             people on their feet. How that difference is measured depends on
             where the camera points: torso angle under an oblique camera,
             torso-to-shoulder foreshortening straight down. Using the angle at
             nadir is not merely weak, it inverts - a body lying on the ground
             projects along the image exactly as a standing body does from the
             side. See posture_from_keypoints.

  stillness  A casualty does not move. Measured per SORT track over a time
             window, with camera motion removed (services/egomotion.py);
             without that compensation a motionless body drifts across the
             frame at exactly the speed of the drone. Strongest from a stable
             overhead hover - precisely where posture is weakest.

  responder  A person standing where one of our own responders reported their
             position is that responder. A hard veto, never a score.

The two vision signals are complementary by construction, which is why they
are fused rather than chained: whichever one the current camera geometry
undermines, the other is in its best regime.
"""
from __future__ import annotations

import math
import os
import threading
import time
from dataclasses import dataclass, field

import numpy as np

from services.egomotion import CameraMotion
from services import responder_registry

# Master switch. Off restores the old behaviour - every person is a casualty -
# which is what a demo on footage with no bystanders may actually want.
CASUALTY_GATE_ENABLED = os.getenv("CASUALTY_GATE", "true").lower() == "true"

# Fused score at or above which a person is promoted to casualty.
CASUALTY_MIN_SCORE = float(os.getenv("CASUALTY_MIN_SCORE", "0.55"))

# Torso angle from vertical. Below UPRIGHT the body is clearly standing; above
# HORIZONTAL it is clearly lying down; between, horizontality ramps linearly.
POSTURE_UPRIGHT_DEG    = float(os.getenv("POSTURE_UPRIGHT_DEG", "25"))
POSTURE_HORIZONTAL_DEG = float(os.getenv("POSTURE_HORIZONTAL_DEG", "65"))

# Bounding-box fallback when no pose model is loaded. The box of a standing
# person is roughly 0.3-0.5 wide-to-tall; a body lying across the view exceeds 1.
POSTURE_BBOX_UPRIGHT_AR    = float(os.getenv("POSTURE_BBOX_UPRIGHT_AR", "0.6"))
POSTURE_BBOX_HORIZONTAL_AR = float(os.getenv("POSTURE_BBOX_HORIZONTAL_AR", "1.4"))

# A torso shorter than this fraction of the box diagonal means the body points
# near the camera axis - a near-nadir view of someone standing, or a body
# foreshortened head-on. The angle is meaningless there, so it is dropped.
POSTURE_MIN_TORSO_RATIO = float(os.getenv("POSTURE_MIN_TORSO_RATIO", "0.18"))

# Camera pitch below the horizon at which the view counts as overhead rather
# than oblique, and the posture measurement switches (see posture_from_keypoints).
POSTURE_NADIR_PITCH_DEG = float(os.getenv("POSTURE_NADIR_PITCH_DEG", "55"))

# Nadir measurement: torso length over shoulder width.
#
# Straight down, the angle of a torso says nothing - a body lying on the ground
# projects along the image exactly as a standing body does from the side. What
# does separate them is foreshortening. Standing, the torso points at the
# camera and collapses to a fraction of the shoulders; lying, it is seen at its
# full length. Measured on the demo clip, a prone adult holds 1.5-1.7 across a
# 4x change in apparent size, because both terms scale with distance.
POSTURE_NADIR_UPRIGHT_RATIO = float(os.getenv("POSTURE_NADIR_UPRIGHT_RATIO", "0.85"))
POSTURE_NADIR_PRONE_RATIO   = float(os.getenv("POSTURE_NADIR_PRONE_RATIO", "1.30"))

# Keypoint confidence below which a joint is treated as not seen.
POSTURE_KP_MIN_CONF = float(os.getenv("POSTURE_KP_MIN_CONF", "0.35"))

# Plausibility limits on the keypoints themselves.
#
# In a crowded frame the pose model will happily hand back a "torso" whose
# shoulder sits on a bus roof or inside the next person's box. Measured on
# stock photographs of people standing, that produced torsos running diagonally
# across the whole image at 45 and 89 degrees, and those were the only standing
# people that survived the gate. A joint outside its own box, or a torso longer
# than the body it belongs to, is not a posture reading - it is a mismatch.
POSTURE_KP_BOX_MARGIN = float(os.getenv("POSTURE_KP_BOX_MARGIN", "0.15"))
POSTURE_MAX_TORSO_RATIO = float(os.getenv("POSTURE_MAX_TORSO_RATIO", "0.8"))

# The window is wall-clock, and it has to be sized against how often frames
# actually reach this code — not against the frame rate of the video. A
# /detect round-trip measures ~2.5-3s on this machine (pose, the victim model,
# ego-motion, JPEG decode), so one subject yields roughly one sample every
# three seconds. An 8s window held three of them, never reached the five it
# required, and stillness was silently never measured at all: every verdict on
# real footage came from posture alone.
#
# 30s with a 15s minimum span is also the better operational statement — "this
# person has not moved for a quarter of a minute" is evidence about a casualty,
# where "has not moved for four seconds" is evidence about a traffic light.
STILLNESS_WINDOW_S     = float(os.getenv("STILLNESS_WINDOW_S", "30"))
STILLNESS_MIN_SAMPLES  = int(os.getenv("STILLNESS_MIN_SAMPLES", "4"))
# Fraction of the window that must actually be spanned before scoring, so a
# burst of frames in one second cannot pass for a steady observation.
STILLNESS_MIN_SPAN_FRACTION = float(os.getenv("STILLNESS_MIN_SPAN_FRACTION", "0.5"))
# Drift across the window, as a fraction of the frame diagonal, at which
# stillness reaches zero. 3% of a 1280x720 frame is about 44px.
STILLNESS_MAX_DRIFT    = float(os.getenv("STILLNESS_MAX_DRIFT", "0.03"))
# Must outlast the window, or a track's history is pruned before it can be scored.
STILLNESS_TRACK_TTL_S  = float(os.getenv("STILLNESS_TRACK_TTL_S", "90"))

# Movement veto, over a short window rather than the stillness one.
#
# Stillness needs 15s of one unbroken track, and a person walking through a
# close shot rarely gives that: at one /detect frame every 2.5-3s they move
# far enough between frames that SORT starts a new track, so the window keeps
# restarting and posture decides alone. Posture is exactly what fails on a
# walker when the camera angle is assumed rather than reported - straight-down
# foreshortening rules read a side-on walker's full torso as a body lying flat.
#
# So nobody is a casualty on first sight. A tracked person must be seen again
# at least MOTION_MIN_SPAN_S later, and must not have moved more than
# MOTION_MAX_BODY_PER_S of their own body length per second between the
# sightings. Measuring in body lengths rather than pixels makes it hold at
# any range: a walker covers ~0.75 body lengths a second whether they fill
# the frame or are 40px tall. A real casualty pays one extra frame (~3s);
# a walker whose track keeps restarting is never confirmed at all.
#
# The limit is loose on purpose. Camera compensation is a partial affine, which
# cannot model the perspective change of a tilted camera climbing or orbiting,
# and at the /detect cadence that residual is the same size as a slow walk:
# measured on the rescue-patrol clip, a body lying still read 0.25-0.31 body
# lengths/s while the drone climbed away from it. 1.0 still stops a walking
# or running track; the posture classifier is what separates slow walkers.
MOTION_WINDOW_S        = float(os.getenv("MOTION_WINDOW_S", "8"))
MOTION_MIN_SPAN_S      = float(os.getenv("MOTION_MIN_SPAN_S", "1.0"))
MOTION_MAX_BODY_PER_S  = float(os.getenv("MOTION_MAX_BODY_PER_S", "1.0"))
# A stillness window that was measured and says "moving" vetoes as well:
# drifting this far over 15-30s is someone walking, crawling off or being carried.
STILLNESS_VETO_BELOW   = float(os.getenv("STILLNESS_VETO_BELOW", "0.3"))

# Fusion weights, used when both signals are available.
POSTURE_WEIGHT   = float(os.getenv("POSTURE_WEIGHT", "0.6"))
STILLNESS_WEIGHT = float(os.getenv("STILLNESS_WEIGHT", "0.4"))

# How far box-shape posture is trusted relative to keypoint posture.
#
# Aspect ratio cannot actually tell posture apart from anything else that makes
# a box wide: two people standing side by side, a vehicle the detector
# mistook for a person, a clump of grass. Measured on real photographs of
# people standing and walking, it promoted four of them to casualty at 0.8.
# It is kept because it is better than nothing as a tiebreaker, and discounted
# because on its own it is not evidence.
POSTURE_BBOX_TRUST = float(os.getenv("POSTURE_BBOX_TRUST", "0.5"))

# COCO-pose keypoint indices.
KP_L_SHOULDER, KP_R_SHOULDER = 5, 6
KP_L_HIP, KP_R_HIP = 11, 12


def _clamp01(v: float) -> float:
    return 0.0 if v < 0.0 else (1.0 if v > 1.0 else v)


def _ramp(value: float, low: float, high: float) -> float:
    """0 at or below `low`, 1 at or above `high`, linear between."""
    if high <= low:
        return 0.0
    return _clamp01((value - low) / (high - low))


@dataclass
class CasualtyVerdict:
    """Why a person was or was not called a casualty - carried on the detection."""
    is_casualty: bool = False
    score: float = 0.0
    posture: float | None = None
    stillness: float | None = None
    responder: str = ""
    reasons: list[str] = field(default_factory=list)

    def as_fields(self) -> dict:
        out: dict = {
            "casualty_score": round(self.score, 3),
            "casualty_reasons": list(self.reasons),
        }
        if self.posture is not None:
            out["posture_score"] = round(self.posture, 3)
        if self.stillness is not None:
            out["stillness_score"] = round(self.stillness, 3)
        if self.responder:
            out["matched_responder"] = self.responder
        return out


# -- Posture ------------------------------------------------------------------

def _inside_box(point, bbox: dict, margin: float = POSTURE_KP_BOX_MARGIN) -> bool:
    """True when a keypoint falls within its own detection box, plus slack."""
    w = max(1.0, float(bbox.get("w", 1)))
    h = max(1.0, float(bbox.get("h", 1)))
    x, y = float(bbox.get("x", 0)), float(bbox.get("y", 0))
    pad_x, pad_y = w * margin, h * margin
    return (x - pad_x) <= point[0] <= (x + w + pad_x) and            (y - pad_y) <= point[1] <= (y + h + pad_y)


def _torso_reliable(torso_len: float, bbox: dict) -> bool:
    diag = math.hypot(max(1.0, float(bbox.get("w", 1))), max(1.0, float(bbox.get("h", 1))))
    return (torso_len / diag) >= POSTURE_MIN_TORSO_RATIO


def posture_from_keypoints(keypoints, bbox: dict, pitch_deg: float | None = None) -> tuple[float | None, str]:
    """
    Horizontality in 0..1 from the shoulder/hip keypoints.

    Which measurement is used depends on where the camera is pointing, because
    the same picture means opposite things at the two extremes:

      oblique (pitch above POSTURE_NADIR_PITCH_DEG)
          The torso angle from vertical. Standing bodies run down the image,
          fallen ones across it. Refuses to answer when the torso is too
          foreshortened for its angle to carry information.

      overhead (at or below that pitch)
          Torso length over shoulder width. Angle is useless here - from
          straight above, a body lying on the sand runs down the image exactly
          as a standing body would from the side, which is precisely how an
          earlier version of this function called a real casualty "upright".
          Foreshortening is what separates them: a standing torso points at the
          lens and collapses, a lying one is seen whole.

    `pitch_deg` is camera pitch below the horizon (-90 = straight down); None
    means unknown, and the oblique measurement is used as the safer default -
    it abstains on foreshortened torsos rather than guessing.
    """
    kps = np.asarray(keypoints, dtype=np.float32)
    if kps.ndim != 2 or kps.shape[0] <= KP_R_HIP or kps.shape[1] < 3:
        return None, "posture_unavailable"

    def joint(idx_a: int, idx_b: int):
        a, b = kps[idx_a], kps[idx_b]
        seen = [p for p in (a, b) if p[2] >= POSTURE_KP_MIN_CONF]
        if not seen:
            return None
        return np.mean([p[:2] for p in seen], axis=0)

    shoulder = joint(KP_L_SHOULDER, KP_R_SHOULDER)
    hip = joint(KP_L_HIP, KP_R_HIP)
    if shoulder is None or hip is None:
        return None, "posture_no_torso"

    # Reject a torso built from joints that cannot belong to this person before
    # measuring anything with it.
    if not _inside_box(shoulder, bbox) or not _inside_box(hip, bbox):
        return None, "posture_keypoints_outside_box"

    vec = hip - shoulder
    torso_len = float(np.hypot(vec[0], vec[1]))
    if torso_len < 1.0:
        return None, "posture_no_torso"

    diag = math.hypot(max(1.0, float(bbox.get("w", 1))), max(1.0, float(bbox.get("h", 1))))
    if torso_len > diag * POSTURE_MAX_TORSO_RATIO:
        # A torso cannot be nearly as long as the diagonal of the box holding
        # the whole body; these joints come from more than one person.
        return None, "posture_torso_implausible"

    if pitch_deg is not None and abs(pitch_deg) >= POSTURE_NADIR_PITCH_DEG:
        left, right = kps[KP_L_SHOULDER], kps[KP_R_SHOULDER]
        if not _inside_box(left[:2], bbox) or not _inside_box(right[:2], bbox):
            return None, "posture_keypoints_outside_box"
        if left[2] < POSTURE_KP_MIN_CONF or right[2] < POSTURE_KP_MIN_CONF:
            # Shoulder width is the yardstick this measurement divides by; with
            # only one shoulder seen there is nothing to normalise against.
            return None, "posture_no_shoulder_width"
        shoulder_w = float(np.hypot(left[0] - right[0], left[1] - right[1]))
        if shoulder_w < 1.0:
            return None, "posture_no_shoulder_width"
        ratio = torso_len / shoulder_w
        return (_ramp(ratio, POSTURE_NADIR_UPRIGHT_RATIO, POSTURE_NADIR_PRONE_RATIO),
                "posture_from_pose_nadir")

    if not _torso_reliable(torso_len, bbox):
        # Foreshortened under an oblique camera: the projection hides the real
        # orientation, and a guess here is how standing people become casualties.
        return None, "posture_foreshortened"

    # 0 deg = torso runs straight down the image (standing), 90 deg = across it.
    angle = abs(math.degrees(math.atan2(abs(float(vec[0])), abs(float(vec[1])))))
    return _ramp(angle, POSTURE_UPRIGHT_DEG, POSTURE_HORIZONTAL_DEG), "posture_from_pose"


def posture_from_bbox(bbox: dict) -> tuple[float, str]:
    """
    Fallback horizontality from box aspect ratio, used when no pose is available.

    Much weaker than the keypoint version - a crouching person and a seated one
    both widen the box - so it is reported under its own reason string and the
    reviewer can see which signal was used.
    """
    w = max(1.0, float(bbox.get("w", 1)))
    h = max(1.0, float(bbox.get("h", 1)))
    return _ramp(w / h, POSTURE_BBOX_UPRIGHT_AR, POSTURE_BBOX_HORIZONTAL_AR), "posture_from_bbox"


# -- Stillness ----------------------------------------------------------------

@dataclass
class _TrackHistory:
    # Centroids in the *current* coordinates of the frame. Every entry is
    # warped forward by the camera transform each frame, so the series
    # describes motion of the subject over the ground rather than across the
    # sensor.
    points: list = field(default_factory=list)  # (t, x, y, body length px)
    last_seen: float = 0.0
    compensated: bool = True


class StillnessMonitor:
    """Per-track motion history, kept in world terms by removing camera motion."""

    def __init__(self) -> None:
        self._tracks: dict[int, _TrackHistory] = {}
        self._lock = threading.Lock()

    def reset(self) -> None:
        with self._lock:
            self._tracks.clear()

    def advance_camera(self, motion: CameraMotion, frame_shape) -> None:
        """
        Re-expresses every stored point in the coordinates of the new frame.

        Called once per frame, before `update`. When the camera estimate failed
        the histories are flagged uncompensated: their drift can no longer be
        told apart from the movement of the drone, so `update` declines to
        score them rather than reporting motion that may not be the subject's.
        """
        h, w = frame_shape[0], frame_shape[1]
        cx, cy = w / 2.0, h / 2.0
        now = time.monotonic()
        with self._lock:
            for hist in self._tracks.values():
                if motion.ok:
                    hist.points = [(t, *motion.apply(x, y, cx, cy), size) for (t, x, y, size) in hist.points]
                else:
                    hist.compensated = False
            stale = [tid for tid, hist in self._tracks.items()
                     if now - hist.last_seen > STILLNESS_TRACK_TTL_S]
            for tid in stale:
                del self._tracks[tid]

    def update(self, track_id: int, bbox: dict, frame_shape) -> tuple[float | None, str]:
        """
        Adds the observation of this frame and returns stillness in 0..1, or None.

        None means "not measured yet" - too few samples, too short a window, or
        camera motion that could not be removed - and is deliberately distinct
        from 0.0, which means "measured, and this subject is moving".
        """
        now = time.monotonic()
        cx = float(bbox.get("x", 0)) + float(bbox.get("w", 0)) / 2.0
        cy = float(bbox.get("y", 0)) + float(bbox.get("h", 0)) / 2.0
        size = max(1.0, float(bbox.get("w", 0)), float(bbox.get("h", 0)))

        with self._lock:
            hist = self._tracks.setdefault(track_id, _TrackHistory())
            hist.points.append((now, cx, cy, size))
            hist.last_seen = now
            hist.points = [p for p in hist.points if now - p[0] <= STILLNESS_WINDOW_S]
            points = list(hist.points)
            compensated = hist.compensated
            if not compensated:
                # Recovery. A failed camera estimate makes every point older
                # than it untrustworthy, so the window is dropped back to this
                # one observation and refilled from here. The earlier version
                # cleared the flag only when the window had already emptied,
                # which for a subject seen every frame never happened - one bad
                # estimate silenced stillness for that track permanently.
                hist.points = [hist.points[-1]]
                hist.compensated = True
                points = list(hist.points)

        if not compensated:
            return None, "stillness_camera_unknown"
        if len(points) < STILLNESS_MIN_SAMPLES:
            return None, "stillness_warming_up"
        if points[-1][0] - points[0][0] < STILLNESS_WINDOW_S * STILLNESS_MIN_SPAN_FRACTION:
            return None, "stillness_window_short"

        xs = np.array([p[1] for p in points], dtype=np.float32)
        ys = np.array([p[2] for p in points], dtype=np.float32)
        # Median centre, max deviation: robust to one bad box, but still
        # sensitive to a subject who walked away and came back.
        drift = float(np.max(np.hypot(xs - np.median(xs), ys - np.median(ys))))
        diag = math.hypot(float(frame_shape[1]), float(frame_shape[0])) or 1.0
        return 1.0 - _clamp01((drift / diag) / STILLNESS_MAX_DRIFT), "stillness_measured"

    def recent_motion(self, track_id: int) -> float | None:
        """
        How fast this track moved over the last MOTION_WINDOW_S, in its own body
        lengths per second. None when it has not been seen twice far enough
        apart yet (or the camera motion was lost), i.e. not measured.

        Call after `update` for the same frame.
        """
        with self._lock:
            hist = self._tracks.get(track_id)
            if hist is None or not hist.points:
                return None
            now = hist.points[-1][0]
            points = [p for p in hist.points if now - p[0] <= MOTION_WINDOW_S]
        if len(points) < 2:
            return None
        first, last = points[0], points[-1]
        span = last[0] - first[0]
        if span < MOTION_MIN_SPAN_S:
            return None
        body = float(np.median([p[3] for p in points]))
        dist = math.hypot(last[1] - first[1], last[2] - first[2])
        return (dist / body) / span


_monitor = StillnessMonitor()


def monitor() -> StillnessMonitor:
    return _monitor


# -- Fusion -------------------------------------------------------------------

def judge(detection: dict, keypoints, frame_shape,
          pitch_deg: float | None = None,
          monitor: StillnessMonitor | None = None) -> CasualtyVerdict:
    """
    Decides whether one person detection is a casualty.

    `monitor` is the stillness history to judge against. Track ids are only
    unique within one video stream, so each feed passes its own; omitted, the
    module-wide monitor is used.

    The detection is expected to carry `bbox`, and `track_id`/`lat`/`lng` when
    available. Missing signals narrow the evidence rather than blocking a
    verdict - a first-frame detection of a clearly prone body should still be
    called, it just scores lower than one a stillness window agrees with.
    """
    verdict = CasualtyVerdict()
    bbox = detection.get("bbox") or {}

    if not CASUALTY_GATE_ENABLED:
        verdict.is_casualty = True
        verdict.score = 1.0
        verdict.reasons = ["gate_disabled"]
        return verdict

    # Hard veto first - no amount of posture evidence outranks knowing who it is.
    #
    # Only ever applied to a detection carrying its OWN ground position. When
    # `subject_located` is false the coordinate is the aircraft's, shared by
    # every detection in the frame, and vetoing on it would let a drone that
    # happens to be over one rescuer suppress a genuine casualty metres away.
    # Missing a casualty is the worse error, so an unlocated detection simply
    # is not eligible for the veto, and says so.
    if detection.get("subject_located"):
        matched, who = responder_registry.is_known_responder(
            detection.get("lat"), detection.get("lng"))
        if matched:
            verdict.responder = who
            verdict.reasons = ["known_responder"]
            return verdict
    elif responder_registry.active():
        verdict.reasons.append("responder_veto_unavailable_no_subject_position")

    posture, posture_reason = (None, "posture_unavailable")
    if keypoints is not None:
        posture, posture_reason = posture_from_keypoints(keypoints, bbox, pitch_deg)
    posture_trusted = posture is not None
    if posture is None:
        posture, posture_reason = posture_from_bbox(bbox)
        posture *= POSTURE_BBOX_TRUST
    verdict.posture = posture
    verdict.reasons.append(posture_reason)

    stillness, stillness_reason = (None, "stillness_untracked")
    motion = None
    track_id = detection.get("track_id")
    if track_id is not None:
        mon = monitor or _monitor
        stillness, stillness_reason = mon.update(int(track_id), bbox, frame_shape)
        motion = mon.recent_motion(int(track_id))
    verdict.stillness = stillness
    verdict.reasons.append(stillness_reason)

    if stillness is None:
        # Posture carries the decision alone. Not renormalised upward: one
        # signal genuinely is weaker evidence than two that agree, and the
        # score should say so rather than flatter itself.
        verdict.score = posture * POSTURE_WEIGHT + (1.0 - POSTURE_WEIGHT) * posture * 0.5
    else:
        verdict.score = posture * POSTURE_WEIGHT + stillness * STILLNESS_WEIGHT

    # A casualty claim needs at least one signal that can actually tell a
    # casualty from a person: keypoint posture, or a stillness window that was
    # genuinely measured. Score alone is not enough, because box shape can
    # reach a high score for reasons that have nothing to do with anyone lying
    # down. Without a qualifying signal the person is reported as a person,
    # which under the default configuration means not reported at all.
    qualifying = posture_trusted or stillness is not None
    if not qualifying:
        verdict.reasons.append("no_qualifying_signal")

    # Movement vetoes everything above (see MOTION_MAX_BODY_PER_S). Untracked
    # detections - a single photo - have no second sighting to wait for, and
    # are judged on posture as before.
    confirmed = True
    if track_id is not None:
        if motion is None:
            verdict.reasons.append("awaiting_second_sighting")
            confirmed = False
        elif motion > MOTION_MAX_BODY_PER_S:
            verdict.reasons.append("moving")
            confirmed = False
        else:
            verdict.reasons.append("not_moving")
    if stillness is not None and stillness < STILLNESS_VETO_BELOW:
        verdict.reasons.append("moved_over_window")
        confirmed = False

    verdict.is_casualty = qualifying and confirmed and verdict.score >= CASUALTY_MIN_SCORE
    return verdict


def reset() -> None:
    """Clears all per-track state - used when a feed restarts, and by tests."""
    _monitor.reset()
