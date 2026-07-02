"""Tests for ClientSession: frame send/receive, frame skipping, resilience."""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
from datetime import UTC, datetime
from unittest.mock import patch

import numpy as np
import websockets.exceptions

from counter_cruiser.client.transport import ClientSession
from counter_cruiser.config.models import ClientSettings
from counter_cruiser.shared.protocol import (
    DetectionMessage,
    ErrorMessage,
    PongMessage,
    serialize,
)


class FakeCapture:
    """Camera fake: yields *frames* in order, then returns None indefinitely."""

    def __init__(self, frames: list[np.ndarray]) -> None:
        self._frames = iter(frames)
        self.released = False

    def open(self, index: int, width: int, height: int) -> tuple[int, int]:
        return (640, 480)

    def read(self) -> np.ndarray | None:
        return next(self._frames, None)

    def release(self) -> None:
        self.released = True


def _blank_frame() -> np.ndarray:
    return np.zeros((480, 640, 3), dtype=np.uint8)


def _default_config(**overrides) -> ClientSettings:
    base = {'frame_skip': 1, 'jpeg_quality': 85}
    base.update(overrides)
    return ClientSettings(**base)


class TestClientSessionSendReceive:
    """Tests for ClientSession.run send/receive behaviour and resilience."""

    async def test_frame_sent_and_detection_matched(self) -> None:
        """Session sends a frame; when detection comes back it calls on_result."""
        results: list[tuple[DetectionMessage, float]] = []

        capture = FakeCapture([_blank_frame()])
        config = _default_config()

        detection_payload = None

        async def fake_connect(url, **kw):
            class FakeWS:
                async def send(self, data: str) -> None:
                    nonlocal detection_payload
                    msg = json.loads(data)
                    # Echo back a detection for the frame id
                    detection_payload = serialize(
                        DetectionMessage(
                            frame_id=msg['frame_id'], boxes=[], processing_time_ms=1.0
                        )
                    )

                def __aiter__(self):
                    return self._iter()

                async def _iter(self):
                    # Wait until detection_payload is set then yield it
                    while detection_payload is None:
                        await asyncio.sleep(0.001)
                    yield detection_payload

                async def close(self):
                    pass

                async def __aenter__(self):
                    return self

                async def __aexit__(self, *_):
                    pass

            return FakeWS()

        session = ClientSession(
            capture=capture,
            config=config,
            on_result=lambda m, lat: results.append((m, lat)),
            reconnect_interval=0.01,
        )

        with patch(
            'counter_cruiser.client.transport.websockets.connect',
            side_effect=fake_connect,
        ):
            task = asyncio.create_task(session.run())
            deadline = asyncio.get_event_loop().time() + 3.0
            while not results and asyncio.get_event_loop().time() < deadline:
                await asyncio.sleep(0.01)
            session.stop()
            await asyncio.wait_for(task, timeout=2.0)

        assert len(results) >= 1
        assert results[0][1] >= 0.0  # latency non-negative

    async def test_frame_skip_sends_every_nth_frame(self) -> None:
        """With frame_skip=3, only 1 in 3 frames is sent."""
        sent_count = 0

        capture = FakeCapture([_blank_frame()] * 9)
        config = _default_config(frame_skip=3)

        class FakeWS:
            async def send(self, data: str) -> None:
                nonlocal sent_count
                if json.loads(data).get('type') == 'frame':
                    sent_count += 1

            def __aiter__(self):
                return self._iter()

            async def _iter(self):
                # Yield nothing; the send loop drains naturally when camera returns None
                if False:
                    yield  # make this an async generator

            async def close(self):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, *_):
                pass

        async def fake_connect(url, **kw):
            return FakeWS()

        session = ClientSession(
            capture=capture,
            config=config,
            on_result=lambda m, lat: None,
            reconnect_interval=0.01,
        )

        with patch(
            'counter_cruiser.client.transport.websockets.connect',
            side_effect=fake_connect,
        ):
            task = asyncio.create_task(session.run())
            await asyncio.sleep(0.2)
            session.stop()
            with contextlib.suppress(Exception):
                await asyncio.wait_for(task, timeout=2.0)

        assert sent_count == 3  # 9 frames / skip=3

    async def test_server_error_message_is_logged(self, caplog) -> None:
        capture = FakeCapture([])
        config = _default_config()

        error_msg = serialize(ErrorMessage(error_type='oops', message='bad things'))

        class FakeWS:
            async def send(self, data: str) -> None:
                pass

            def __aiter__(self):
                return self._iter()

            async def _iter(self):
                yield error_msg

            async def close(self):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, *_):
                pass

        async def fake_connect(url, **kw):
            return FakeWS()

        session = ClientSession(
            capture=capture,
            config=config,
            on_result=lambda m, lat: None,
            reconnect_interval=0.01,
        )
        with (
            caplog.at_level(logging.ERROR, logger='counter_cruiser.client.transport'),
            patch(
                'counter_cruiser.client.transport.websockets.connect',
                side_effect=fake_connect,
            ),
        ):
            task = asyncio.create_task(session.run())
            await asyncio.sleep(0.1)
            session.stop()
            with contextlib.suppress(Exception):
                await asyncio.wait_for(task, timeout=2.0)

        assert any('oops' in r.message for r in caplog.records)

    async def test_unrecognized_message_type_is_ignored(self) -> None:
        capture = FakeCapture([])
        config = _default_config()
        results: list = []

        pong_msg = serialize(PongMessage(ping_timestamp=datetime.now(tz=UTC)))

        class FakeWS:
            async def send(self, data: str) -> None:
                pass

            def __aiter__(self):
                return self._iter()

            async def _iter(self):
                yield pong_msg

            async def close(self):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, *_):
                pass

        async def fake_connect(url, **kw):
            return FakeWS()

        session = ClientSession(
            capture=capture,
            config=config,
            on_result=lambda m, lat: results.append(m),
            reconnect_interval=0.01,
        )
        with patch(
            'counter_cruiser.client.transport.websockets.connect',
            side_effect=fake_connect,
        ):
            task = asyncio.create_task(session.run())
            await asyncio.sleep(0.1)
            session.stop()
            with contextlib.suppress(Exception):
                await asyncio.wait_for(task, timeout=2.0)

        assert results == []

    async def test_camera_released_on_stop(self) -> None:
        capture = FakeCapture([])
        config = _default_config()

        async def fake_connect(url, **kw):
            raise OSError('refused')

        session = ClientSession(
            capture=capture,
            config=config,
            on_result=lambda m, lat: None,
            reconnect_interval=0.01,
        )
        with patch(
            'counter_cruiser.client.transport.websockets.connect',
            side_effect=fake_connect,
        ):
            task = asyncio.create_task(session.run())
            await asyncio.sleep(0.05)
            session.stop()
            await asyncio.wait_for(task, timeout=2.0)

        assert capture.released is True

    async def test_mid_connection_drop_triggers_reconnect(self) -> None:
        """A WebSocketException raised mid-connection cancels the loops and
        triggers a reconnect via the outer retry handler."""
        connect_count = 0

        capture = FakeCapture([_blank_frame()] * 50)
        config = _default_config()

        class FakeWS:
            async def send(self, data: str) -> None:
                raise websockets.exceptions.ConnectionClosedOK(None, None)

            def __aiter__(self):
                return self._iter()

            async def _iter(self):
                await asyncio.sleep(1000)
                if False:
                    yield  # make this an async generator

            async def close(self):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, *_):
                pass

        async def fake_connect(url, **kw):
            nonlocal connect_count
            connect_count += 1
            return FakeWS()

        session = ClientSession(
            capture=capture,
            config=config,
            on_result=lambda m, lat: None,
            reconnect_interval=0.01,
        )

        with patch(
            'counter_cruiser.client.transport.websockets.connect',
            side_effect=fake_connect,
        ):
            task = asyncio.create_task(session.run())
            deadline = asyncio.get_event_loop().time() + 2.0
            while connect_count < 2 and asyncio.get_event_loop().time() < deadline:
                await asyncio.sleep(0.01)
            session.stop()
            await asyncio.wait_for(task, timeout=2.0)

        assert connect_count >= 2

    async def test_frame_height_reflects_actual_camera_resolution(self) -> None:
        """frame_height exposes the camera's negotiated height, not the configured one.

        Cameras do not always honor the requested resolution; the elevated/floor
        ratio decision must use what the camera actually negotiated.
        """

        class MismatchedCapture(FakeCapture):
            def open(self, index: int, width: int, height: int) -> tuple[int, int]:
                return (640, 720)  # camera ignores the configured height (480)

        capture = MismatchedCapture([])
        config = _default_config()
        assert config.frame_height == 480

        session = ClientSession(
            capture=capture,
            config=config,
            on_result=lambda m, lat: None,
            reconnect_interval=0.01,
        )

        assert session.frame_height == config.frame_height  # before open()

        async def fake_connect(url, **kw):
            raise OSError('refused')

        with patch(
            'counter_cruiser.client.transport.websockets.connect',
            side_effect=fake_connect,
        ):
            task = asyncio.create_task(session.run())
            deadline = asyncio.get_event_loop().time() + 2.0
            while session.frame_height == config.frame_height and (
                asyncio.get_event_loop().time() < deadline
            ):
                await asyncio.sleep(0.01)
            session.stop()
            await asyncio.wait_for(task, timeout=2.0)

        assert session.frame_height == 720
        assert session.frame_height != config.frame_height

    async def test_stop_during_reconnect_attempt_breaks_immediately(self) -> None:
        """Calling stop() while a reconnect attempt fails exits without sleeping."""
        capture = FakeCapture([])
        config = _default_config()
        session = ClientSession(
            capture=capture,
            config=config,
            on_result=lambda m, lat: None,
            reconnect_interval=5.0,
        )

        async def fake_connect(url, **kw):
            session.stop()
            raise OSError('refused')

        with patch(
            'counter_cruiser.client.transport.websockets.connect',
            side_effect=fake_connect,
        ):
            task = asyncio.create_task(session.run())
            # The long reconnect_interval would block the test if the
            # `if not self._running: break` short-circuit weren't taken.
            await asyncio.wait_for(task, timeout=2.0)

        assert capture.released is True


class TestFrameRingBuffer:
    async def test_get_frame_returns_retained_frame(self) -> None:
        frame = _blank_frame()
        capture = FakeCapture([frame])
        config = _default_config()
        session = ClientSession(
            capture=capture, config=config, on_result=lambda *_: None
        )

        async def fake_ws_send(_data: str) -> None:
            session.stop()

        class FakeWS:
            async def send(self, data: str) -> None:
                await fake_ws_send(data)

            async def close(self) -> None:
                return None

        await session._send_loop(FakeWS())

        assert session.get_frame(1) is not None
        np.testing.assert_array_equal(session.get_frame(1), frame)

    async def test_get_frame_returns_none_for_unknown_id(self) -> None:
        capture = FakeCapture([])
        config = _default_config()
        session = ClientSession(
            capture=capture, config=config, on_result=lambda *_: None
        )
        assert session.get_frame(999) is None

    async def test_ring_buffer_evicts_oldest_beyond_capacity(self) -> None:
        frames = [_blank_frame() for _ in range(5)]
        capture = FakeCapture(frames)
        config = _default_config()
        session = ClientSession(
            capture=capture,
            config=config,
            on_result=lambda *_: None,
            frame_buffer_capacity=3,
        )

        class FakeWS:
            sent = 0

            async def send(self, data: str) -> None:
                FakeWS.sent += 1
                if FakeWS.sent >= 5:
                    session.stop()

            async def close(self) -> None:
                return None

        await session._send_loop(FakeWS())

        # Capacity 3, 5 frames sent: ids 1 and 2 evicted, 3/4/5 retained.
        assert session.get_frame(1) is None
        assert session.get_frame(2) is None
        assert session.get_frame(3) is not None
        assert session.get_frame(4) is not None
        assert session.get_frame(5) is not None
