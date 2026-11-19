"""
The casualty hold (services/casualty.CASUALTY_HOLD_S): a tracked subject is
reported as a casualty only once it has been judged one, without a break, for
that long. On the 17 Nov 2026 staged footage a striped pole and walkers were
called casualties for one to three seconds; the staged victims stayed
casualties frame after frame.
"""
import pytest

from services import casualty

FRAME = (720, 1280, 3)
LYING = {"bbox": {"x": 500, "y": 300, "w": 120, "h": 40}, "track_id": 7, "model_down": 0.99}
BURIED = {"bbox": {"x": 500, "y": 300, "w": 30, "h": 30}, "track_id": 8, "partial": True}


@pytest.fixture(autouse=True)
def _hold(monkeypatch):
    casualty.reset()
    monkeypatch.setattr(casualty, "CASUALTY_HOLD_S", 3.0)
    clock = [1000.0]
    monkeypatch.setattr(casualty.time, "monotonic", lambda: clock[0])
    return clock


def _sightings(clock, det, times, down=None):
    out = []
    for i, t in enumerate(times):
        clock[0] = 1000.0 + t
        d = dict(det)
        if down is not None:
            d["model_down"] = down[i]
        out.append(casualty.judge(d, None, FRAME))
    return out


def test_a_casualty_seen_for_three_seconds_is_reported(_hold):
    v = _sightings(_hold, LYING, [0, 1, 2, 3, 4])
    # Sighting 2 (t=1) is the first casualty verdict; the hold runs from there.
    assert [x.is_casualty for x in v] == [False, False, False, False, True]
    assert "casualty_holding" in v[2].reasons


def test_a_two_second_glimpse_is_not_reported(_hold):
    v = _sightings(_hold, LYING, [0, 1, 2, 3])
    assert not any(x.is_casualty for x in v)


def test_a_non_casualty_verdict_restarts_the_hold(_hold):
    # Read as standing at t=3: the run starting at t=1 is broken, the next starts at t=4.
    v = _sightings(_hold, LYING, [0, 1, 2, 3, 4, 5, 6, 7], down=[.99, .99, .99, .01, .99, .99, .99, .99])
    assert [x.is_casualty for x in v] == [False] * 7 + [True]


def test_the_hold_is_in_seconds_not_frames(_hold):
    # Three frames a second: still three seconds before the first report.
    times = [i / 3 for i in range(16)]
    v = _sightings(_hold, LYING, times)
    first = next(t for t, x in zip(times, v) if x.is_casualty)
    assert first >= 3.0 + 1.0 - 1e-6   # first casualty verdict at ~1 s (MOTION_MIN_SPAN_S), then 3 s


def test_each_track_holds_on_its_own(_hold):
    other = dict(LYING, track_id=99)
    _sightings(_hold, LYING, [0, 1, 2, 3])
    v = _sightings(_hold, other, [4])
    assert not v[0].is_casualty
    assert _sightings(_hold, LYING, [4])[0].is_casualty


def test_a_partly_buried_person_is_held_too(_hold):
    v = _sightings(_hold, BURIED, [0, 1, 2, 3, 4])
    assert [x.is_casualty for x in v] == [False, False, False, False, True]


def test_an_untracked_photo_is_not_held(_hold):
    det = {k: v for k, v in LYING.items() if k != "track_id"}
    assert _sightings(_hold, det, [0])[0].is_casualty


def test_zero_turns_the_hold_off(_hold, monkeypatch):
    monkeypatch.setattr(casualty, "CASUALTY_HOLD_S", 0.0)
    v = _sightings(_hold, LYING, [0, 1])
    assert v[1].is_casualty
