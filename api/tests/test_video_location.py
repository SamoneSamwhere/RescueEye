"""Reading where a video was filmed from its own metadata (services/video_location.py)."""
from services import video_location as vl

DJI_NEW = """1
00:00:00,000 --> 00:00:00,033
<font size="28">FrameCnt: 1, DiffTime: 33ms
2026-11-08 10:00:00.000
[iso: 100] [shutter: 1/1000.0] [fnum: 2.8] [ev: 0] [focal_len: 24.00] [latitude: 10.338512] [longitude: 123.911803] [rel_alt: 35.200 abs_alt: 60.100] [ct: 5500] </font>

2
00:00:00,033 --> 00:00:00,066
[latitude: 10.338513] [longitude: 123.911804] [rel_alt: 35.200 abs_alt: 60.100]

3
00:00:01,033 --> 00:00:01,066
[latitude: 10.338600] [longitude: 123.911900] [rel_alt: 36.000 abs_alt: 61.000]
"""

DJI_OLD = """1
00:00:00,000 --> 00:00:01,000
HOME(123.9110,10.3380) 2026.11.08 10:00:00
GPS(123.9118,10.3385,19) BAROMETER:30.5
ISO:100 Shutter:500 EV:0 Fnum:F2.8 H 30.5m

2
00:00:01,000 --> 00:00:02,000
GPS(0.0,0.0,0) H 0.0m
"""


def test_new_dji_captions_become_a_one_per_second_track():
    track = vl.parse_srt(DJI_NEW)
    assert track == [[0.0, 10.338512, 123.911803, 35.2], [1.03, 10.3386, 123.9119, 36.0]]


def test_old_dji_captions_put_longitude_first_and_skip_no_fix():
    assert vl.parse_srt(DJI_OLD) == [[0.0, 10.3385, 123.9118, 30.5]]


def test_phone_header_location():
    assert vl.parse_iso6709("+10.3385+123.9118+012.000/") == (10.3385, 123.9118)
    assert vl.parse_iso6709("-33.8688+151.2093/") == (-33.8688, 151.2093)
    assert vl.parse_iso6709("nonsense") is None


def test_captions_file_wins_and_track_follows_playback(tmp_path):
    geo = vl.read_location(tmp_path / "missing.mp4", DJI_NEW)
    assert geo.method == "srt_file" and geo.source == "video_metadata"
    assert geo.at(0.5)[:2] == (10.338512, 123.911803)
    assert geo.at(5.0)[:2] == (10.3386, 123.9119)
    assert vl.VideoGeo.from_dict(geo.to_dict()) == geo


def test_no_position_anywhere(tmp_path):
    assert vl.read_location(tmp_path / "missing.mp4", "not captions") is None


def test_detections_from_a_library_clip_use_where_it_was_filmed(monkeypatch):
    from types import SimpleNamespace
    from routers import detect
    from services import feed_registry
    geo = vl.read_location(None, DJI_NEW)
    feed = SimpleNamespace(geo=geo, media_drone_id="alpha", playback_sec=lambda: 3.0, drone_id=None)
    monkeypatch.setattr(feed_registry, "get_feed", lambda key: feed)
    loc = detect._drone_location("feed9")
    assert (loc.lat, loc.lng, loc.altitude_m) == (10.3386, 123.9119, 36.0)
    assert (loc.source, loc.drone_id, loc.can_georeference) == ("video_metadata", "alpha", False)
