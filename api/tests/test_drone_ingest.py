"""
Always-on drone ingest (services/drone_ingest.py).

What must hold: a drone that goes live gets a feed on its own; a short drop
keeps the panel; a drone gone for the grace period has its feed closed; a feed
an operator closed by hand stays closed until that drone stops and goes live
again; each drone's address is derived from its name; and only registered
drones get a feed at all.
"""
import pytest

from services import drone_ingest, feed_registry


@pytest.fixture(autouse=True)
def clean(monkeypatch):
    # No real FFmpeg: a feed just needs to exist in the registry.
    monkeypatch.setattr(feed_registry, "_start_producer", lambda feed: None)
    feed_registry.shutdown_all()
    drone_ingest.reset()
    drone_ingest.set_registered([{"id": 1, "callsign": "Alpha"}, {"id": 2, "callsign": "Bravo"}])
    yield
    feed_registry.shutdown_all()
    drone_ingest.reset()


def ingest_feeds():
    return [f for f in feed_registry.list_feeds() if f.ingest_path]


def test_going_live_opens_a_feed_reading_the_local_stream():
    drone_ingest.sync({"live/alpha-1": {}}, now=0)
    (feed,) = ingest_feeds()
    assert feed.ingest_path == "live/alpha-1"
    assert feed.source == f"rtsp://127.0.0.1:{drone_ingest.RTSP_PORT}/live/alpha-1"
    assert feed.label == "Alpha"
    assert feed.kind == "live"


def test_staying_live_does_not_open_a_second_feed():
    drone_ingest.sync({"live/alpha-1": {}}, now=0)
    drone_ingest.sync({"live/alpha-1": {}}, now=1)
    assert len(ingest_feeds()) == 1


def test_a_short_drop_keeps_the_feed_and_a_long_one_closes_it():
    drone_ingest.sync({"live/alpha-1": {}}, now=0)
    drone_ingest.sync({}, now=drone_ingest.GRACE_S - 1)
    assert len(ingest_feeds()) == 1
    drone_ingest.sync({}, now=drone_ingest.GRACE_S + 1)
    assert ingest_feeds() == []


def test_two_drones_get_two_feeds():
    drone_ingest.sync({"live/alpha-1": {}, "live/bravo-2": {}}, now=0)
    assert sorted(f.ingest_path for f in ingest_feeds()) == ["live/alpha-1", "live/bravo-2"]


def test_a_feed_closed_by_hand_stays_closed_until_the_drone_restarts():
    drone_ingest.sync({"live/alpha-1": {}}, now=0)
    (feed,) = ingest_feeds()
    feed_registry.remove_feed(feed.id)              # operator closes the panel
    drone_ingest.sync({"live/alpha-1": {}}, now=1)
    assert ingest_feeds() == []                     # not reopened while still live
    drone_ingest.sync({}, now=2)                    # drone stops
    drone_ingest.sync({"live/alpha-1": {}}, now=3)    # and goes live again
    assert len(ingest_feeds()) == 1


def test_full_feed_slots_do_not_crash_the_watcher():
    for i in range(feed_registry.MAX_FEEDS):
        feed_registry.add_feed(source="", label=f"other {i}")
    drone_ingest.sync({"live/alpha-1": {}}, now=0)
    assert ingest_feeds() == []


@pytest.mark.parametrize("name, path", [
    ("DJI Neo 2", "live/dji-neo-2"),
    ("  Alpha__1 ", "live/alpha-1"),
    ("", "live/drone"),
    ("!!!", "live/drone"),
])
def test_stream_address_comes_from_the_drone_name(name, path):
    assert drone_ingest.stream_path(name) == path


def test_an_unregistered_drone_gets_no_feed():
    drone_ingest.sync({"live/intruder": {}, "live/alpha": {}}, now=0)
    assert ingest_feeds() == []


def test_a_drone_removed_from_the_registry_has_its_feed_closed():
    drone_ingest.sync({"live/alpha-1": {}}, now=0)
    drone_ingest.set_registered([{"id": 2, "callsign": "Bravo"}])
    drone_ingest.sync({"live/alpha-1": {}}, now=drone_ingest.GRACE_S + 1)
    assert ingest_feeds() == []


def test_a_just_registered_drone_is_accepted_at_once():
    path = drone_ingest.remember(7, "DJI Neo 2")
    assert path == "live/dji-neo-2-7"
    drone_ingest.sync({path: {}}, now=0)
    (feed,) = ingest_feeds()
    assert feed.label == "DJI Neo 2"
