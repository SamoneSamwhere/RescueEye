"""
Decision support for one casualty: how urgent, and how many responders.

Detection (YOLO, on this machine) says *there is a casualty here*. This is the
step after it: given what detection found out about the person and the scene,
suggest an incident priority and a team size. Command Staff see both as a
suggestion and decide.

Two engines answer the same two questions:

  * Jev (TypeSafe AI), a hosted "System One" model that returns typed,
    calibrated decisions - a choice plus its probabilities - instead of text.
    Used when TYPESAFE_API_KEY is set. Only the facts below are sent: never
    the image, never the location.
  * Rules, the fallback: no key, no internet (the normal state of a disaster
    zone), or Jev failing. Same answer shape, labelled source="rules".

Facts used: partly buried, not moving, lying down, how sure the casualty gate
was, and the scene damage (collapse, flood, fire) around the person. A drone
cannot weigh someone, so body size is not used.
"""
from __future__ import annotations

import json
import logging
import os
import threading
from collections import OrderedDict

logger = logging.getLogger("rescueeye.assessment")

JEV_URL = os.getenv("TYPESAFE_API_URL", "https://api.typesafe.ai/v1/systemone")
JEV_MODEL = os.getenv("TYPESAFE_MODEL", "jev-latest")
JEV_TIMEOUT_S = float(os.getenv("TYPESAFE_TIMEOUT_S", "4"))

PRIORITIES = ("LOW", "MEDIUM", "HIGH", "CRITICAL")
TEAM_SIZES = ("1", "2", "3", "4+")

_SCENE_WORDS = {
    "structural_damage": "collapsed or damaged structure",
    "flood_damage": "flooding",
    "fire_damage": "fire",
    "no_damage": "no visible damage",
}

# The questions Jev answers. Criteria descriptions are what the model weighs
# each option against, so they say what each answer means in the field.
QUESTIONS = {
    "priority": {
        "type": "choice",
        "instructions": "How urgent is the rescue of this disaster casualty?",
        "criteria": {
            "LOW": "Person probably fine or able to move; no hazard around them.",
            "MEDIUM": "Possibly hurt, not trapped, no immediate hazard.",
            "HIGH": "Likely injured or unable to move, or near a hazard.",
            "CRITICAL": "Trapped or partly buried, motionless, or in fire, flood or a collapse.",
        },
    },
    "responders": {
        "type": "choice",
        "instructions": "How many rescuers does this casualty need on site to be reached and carried out safely?",
        "criteria": {
            "1": "One rescuer: the person can walk out with help.",
            "2": "Two rescuers: carry on a stretcher over clear ground.",
            "3": "Three rescuers: stretcher carry over rubble or water, or one person keeps watch on a hazard.",
            "4+": "Four or more: debris must be lifted or cut away, or a difficult extraction.",
        },
    },
}


def facts_from(payload: dict) -> dict:
    """The casualty as plain facts, from what the web app holds about it."""
    reasons = set(payload.get("casualtyReasons") or [])
    scene = payload.get("scene") or {}
    label = scene.get("label")
    return {
        "partly_buried": "partly_buried" in reasons,
        "not_moving": "not_moving" in reasons,
        "moving": "moving" in reasons,
        "lying_down": bool(reasons & {"posture_from_pose", "posture_from_pose_nadir",
                                      "posture_from_model", "posture_from_bbox"}) and "upright" not in reasons,
        "casualty_certainty": round(float(payload.get("casualtyScore") or payload.get("confidence") or 0), 2),
        "scene": _SCENE_WORDS.get(label, "unknown") if label else "unknown",
        "scene_severity": (scene.get("severity") or "unknown").lower() if label else "unknown",
    }


def _rules(f: dict) -> dict:
    """Plain rules a commander could check by hand; the fallback answer."""
    why: list[str] = []
    hazard = f["scene"] in ("collapsed or damaged structure", "flooding", "fire")

    p = 1                                   # MEDIUM
    if f["casualty_certainty"] >= 0.6 or f["not_moving"] or f["lying_down"]:
        p = 2
    if f["partly_buried"]:
        p = 3
        why.append("partly buried")
    if f["not_moving"]:
        why.append("not moving")
    if hazard:
        p = min(p + 1, 3)
        why.append(f["scene"])
    if f["casualty_certainty"] >= 0.85 and f["not_moving"]:
        p = 3
    if f["moving"] and not f["partly_buried"] and not hazard:
        p = min(p, 1)
        why.append("moving")

    team = 2                                # stretcher carry
    if f["scene"] in ("flooding", "fire", "collapsed or damaged structure"):
        team = 3
    if f["partly_buried"]:
        team = 4
    if f["moving"] and not f["partly_buried"] and not hazard:
        team = 1

    return {
        "priority": PRIORITIES[p], "priorityConfidence": None,
        "responders": TEAM_SIZES[team - 1], "respondersConfidence": None,
        "source": "rules", "model": None,
        "why": why or ["no aggravating signs"],
    }


def _from_jev(body: dict, f: dict) -> dict:
    answers = body["answers"]
    pr, rs = answers["priority"], answers["responders"]
    if pr.get("choice") not in PRIORITIES or rs.get("choice") not in TEAM_SIZES:
        raise ValueError(f"unexpected Jev answer: {pr.get('choice')!r}, {rs.get('choice')!r}")
    rule = _rules(f)
    return {
        "priority": pr["choice"], "priorityConfidence": round(float(pr.get("confidence", 0)), 2),
        "priorityProbabilities": pr.get("probabilities"),
        "responders": rs["choice"], "respondersConfidence": round(float(rs.get("confidence", 0)), 2),
        "respondersProbabilities": rs.get("probabilities"),
        "source": "jev", "model": body.get("model"),
        # The facts that drove it, in the same words as the rules use.
        "why": rule["why"],
    }


# Same facts, same answer: a casualty re-detected every few seconds must not
# cost a Jev call each time.
_cache: "OrderedDict[str, dict]" = OrderedDict()
_cache_lock = threading.Lock()
_CACHE_MAX = 256


def jev_enabled() -> bool:
    return bool(os.getenv("TYPESAFE_API_KEY"))


async def assess(payload: dict) -> dict:
    f = facts_from(payload)
    key = json.dumps(f, sort_keys=True)
    with _cache_lock:
        if key in _cache:
            return {**_cache[key], "facts": f}

    result = None
    if jev_enabled():
        from services.http_client import get_client
        try:
            client = await get_client()
            res = await client.post(
                JEV_URL,
                headers={"Authorization": f"Bearer {os.getenv('TYPESAFE_API_KEY')}"},
                json={"state": json.dumps(f), "model": JEV_MODEL, "questions": QUESTIONS},
                timeout=JEV_TIMEOUT_S,
            )
            res.raise_for_status()
            result = _from_jev(res.json(), f)
        except Exception as exc:
            # Never the key, never the payload: just what went wrong.
            logger.warning(f"[assessment] Jev unavailable ({type(exc).__name__}: {exc}) - using rules")
    if result is None:
        result = _rules(f)
        if jev_enabled():
            result["note"] = "Jev could not be reached; this is the rules-based estimate."

    if result["source"] == "jev":            # only cache the real answer; retry Jev next time
        with _cache_lock:
            _cache[key] = result
            while len(_cache) > _CACHE_MAX:
                _cache.popitem(last=False)
    return {**result, "facts": f}
