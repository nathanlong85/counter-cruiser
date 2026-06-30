"""Tests for the WebSocket connection handler."""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import numpy as np

from counter_cruiser.server.handler import handle_connection
from counter_cruiser.server.model import DetectionModel
from counter_cruiser.shared.protocol import (
    BoundingBox,
    PingMessage,
    PongMessage,
    deserialize,
    encode_frame,
    serialize,
)


class FakeModel(DetectionModel):
    def __init__(self, boxes: list[BoundingBox] | None = None) -> None:
        self._boxes = boxes or []

    def detect(self, frame: np.ndarray) -> list[BoundingBox]:
        return self._boxes


def _fake_ws(messages: list[str]) -> MagicMock:
    """Build a mock websocket that yields *messages* then stops."""
    ws = MagicMock()
    ws.remote_address = ('127.0.0.1', 12345)
    ws.__aiter__ = MagicMock(return_value=aiter_from(messages))
    ws.send = AsyncMock()  # type: ignore[assignment]
    return ws


def aiter_from(items: list):
    """Async iterator over *items*."""
    async def _gen():
        for item in items:
            yield item
    return _gen()


class TestHandleConnection:
    async def test_valid_frame_returns_detection(
        self, sample_frame: np.ndarray
    ) -> None:
        box = BoundingBox(
            x1=0,
            y1=0,
            x2=50,
            y2=100,
            confidence=0.9,
            class_id=16,
            class_name='dog',
        )
        model = FakeModel([box])
        frame_msg = encode_frame(sample_frame, frame_id=1, quality=85)
        ws = _fake_ws([serialize(frame_msg)])

        await handle_connection(ws, model)

        ws.send.assert_called_once()
        sent = json.loads(ws.send.call_args[0][0])
        assert sent['type'] == 'detection'
        assert sent['frame_id'] == 1
        assert len(sent['boxes']) == 1

    async def test_ping_is_answered_with_pong(self) -> None:
        ping = PingMessage()
        ws = _fake_ws([serialize(ping)])
        await handle_connection(ws, FakeModel())

        ws.send.assert_called_once()
        sent_str = ws.send.call_args[0][0]
        pong = deserialize(sent_str)
        assert isinstance(pong, PongMessage)
        assert pong.ping_timestamp == ping.timestamp

    async def test_processing_error_sends_error_message_and_continues(
        self, sample_frame: np.ndarray
    ) -> None:
        class BrokenModel(DetectionModel):
            def detect(self, frame: np.ndarray) -> list[BoundingBox]:
                raise RuntimeError('GPU exploded')

        frame_msg = encode_frame(sample_frame, frame_id=5, quality=85)
        ws = _fake_ws([serialize(frame_msg)])
        await handle_connection(ws, BrokenModel())

        ws.send.assert_called_once()
        sent = json.loads(ws.send.call_args[0][0])
        assert sent['type'] == 'error'
        assert sent['frame_id'] == 5

    async def test_multiple_frames_processed_independently(
        self, sample_frame: np.ndarray
    ) -> None:
        model = FakeModel()
        frames = [serialize(encode_frame(sample_frame, i, 85)) for i in range(3)]
        ws = _fake_ws(frames)
        await handle_connection(ws, model)
        assert ws.send.call_count == 3
