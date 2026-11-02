"""The H.264 live view: frame splitting, slow viewers, and the socket's sign-in."""
import asyncio
import struct

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from routers import stream
from services import auth, video_stream
from services import feed_registry as registry

AUD = b"\x00\x00\x00\x01\x09\xf0"
IDR = b"\x00\x00\x00\x01\x65\x88\x84"     # NAL type 5
P = b"\x00\x00\x00\x01\x41\x9a\x02"       # NAL type 1
SPS = b"\x00\x00\x00\x01\x67\x42\xc0\x1f"


def test_output_is_split_into_whole_frames_and_the_tail_is_kept():
    key, delta = AUD + SPS + IDR, AUD + P
    frames, rest = video_stream.split_frames(key + delta + AUD + b"\x00\x00\x00\x01\x41")
    assert frames == [key, delta]
    # The last frame may still be arriving: it waits for the next delimiter.
    assert rest == AUD + b"\x00\x00\x00\x01\x41"
    assert video_stream.split_frames(AUD + P) == ([], AUD + P)


def test_keyframes_are_recognised():
    assert video_stream.is_keyframe(AUD + SPS + IDR)
    assert not video_stream.is_keyframe(AUD + P)


def test_message_header_carries_keyframe_flag_and_send_time():
    packed = video_stream.pack(b"abc", True, 1234.5)
    assert packed[0] == 1
    assert struct.unpack("<d", packed[1:9])[0] == 1234.5
    assert packed[9:] == b"abc"


def test_a_viewer_starts_at_a_keyframe_and_a_slow_one_skips_ahead():
    loop = asyncio.new_event_loop()
    try:
        viewer = video_stream._Viewer(loop)
        viewer._offer(b"P", False)                 # nothing to decode it against
        assert viewer.queue.empty()
        viewer._offer(b"K", True)
        viewer._offer(b"P", False)
        assert viewer.queue.qsize() == 2

        for _ in range(video_stream.MAX_QUEUED_FRAMES):
            viewer._offer(b"P", False)
        # Over a second behind: the backlog is dropped, and P-frames are refused
        # until a keyframe gives the decoder a clean place to resume.
        assert viewer.queue.empty()
        viewer._offer(b"P", False)
        assert viewer.queue.empty()
        viewer._offer(b"K", True)
        assert viewer.queue.get_nowait() == b"K"
    finally:
        loop.close()


@pytest.fixture()
def ws_client():
    app = FastAPI()
    app.include_router(stream.ws_router, prefix="/stream")
    return TestClient(app)


def test_video_socket_requires_sign_in(ws_client):
    feed = registry.add_feed(source="", label="A")
    try:
        with pytest.raises(WebSocketDisconnect) as exc:
            with ws_client.websocket_connect(f"/stream/feeds/{feed.id}/video?token=nope"):
                pass
        assert exc.value.code == 4401
    finally:
        registry.remove_feed(feed.id)


def test_video_socket_for_unknown_feed_is_closed(ws_client):
    token = auth.issue_token("1", "COMMAND_STAFF", "1")
    with pytest.raises(WebSocketDisconnect) as exc:
        with ws_client.websocket_connect(f"/stream/feeds/missing/video?token={token}"):
            pass
    assert exc.value.code == 4404
