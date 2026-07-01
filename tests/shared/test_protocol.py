"""Tests for typed WebSocket protocol models."""

from __future__ import annotations

import json
from datetime import UTC, datetime

import numpy as np
import pytest
from pydantic import ValidationError

from counter_cruiser.shared.protocol import (
    BoundingBox,
    DetectionMessage,
    ErrorMessage,
    FrameMessage,
    PingMessage,
    PongMessage,
    decode_frame,
    deserialize,
    encode_frame,
    make_error,
    make_pong,
    serialize,
)


class TestMessageModels:
    def test_bounding_box_fields(self) -> None:
        box = BoundingBox(
            x1=10,
            y1=20,
            x2=100,
            y2=200,
            confidence=0.9,
            class_id=16,
            class_name='dog',
        )
        assert box.x1 == 10
        assert box.confidence == 0.9
        assert box.class_name == 'dog'

    def test_frame_message_has_type_discriminator(self) -> None:
        msg = FrameMessage(frame_id=1, image_data='abc', width=640, height=480)
        assert msg.type == 'frame'

    def test_detection_message_has_type_discriminator(self) -> None:
        msg = DetectionMessage(frame_id=1, boxes=[], processing_time_ms=12.5)
        assert msg.type == 'detection'

    def test_error_message_has_type_discriminator(self) -> None:
        msg = ErrorMessage(error_type='oops', message='something broke')
        assert msg.type == 'error'

    def test_ping_has_type_discriminator(self) -> None:
        assert PingMessage().type == 'ping'

    def test_pong_has_type_discriminator(self) -> None:
        ping = PingMessage()
        assert PongMessage(ping_timestamp=ping.timestamp).type == 'pong'

    def test_all_messages_carry_timestamp(self) -> None:
        for msg in [
            FrameMessage(frame_id=1, image_data='x', width=1, height=1),
            DetectionMessage(frame_id=1, boxes=[], processing_time_ms=0.0),
            ErrorMessage(error_type='e', message='m'),
            PingMessage(),
            PongMessage(ping_timestamp=datetime.now(UTC)),
        ]:
            assert isinstance(msg.timestamp, datetime)


class TestSerializeDeserialize:
    def test_round_trip_frame_message(self) -> None:
        original = FrameMessage(frame_id=42, image_data='abc==', width=640, height=480)
        restored = deserialize(serialize(original))
        assert isinstance(restored, FrameMessage)
        assert restored.frame_id == 42
        assert restored.image_data == 'abc=='

    def test_round_trip_detection_message(self) -> None:
        box = BoundingBox(
            x1=0,
            y1=0,
            x2=10,
            y2=10,
            confidence=0.8,
            class_id=16,
            class_name='dog',
        )
        original = DetectionMessage(frame_id=7, boxes=[box], processing_time_ms=5.0)
        restored = deserialize(serialize(original))
        assert isinstance(restored, DetectionMessage)
        assert restored.boxes[0].confidence == pytest.approx(0.8)

    def test_deserialize_dispatches_by_type(self) -> None:
        raw = json.dumps(
            {
                'type': 'ping',
                'timestamp': datetime.now(UTC).isoformat(),
            }
        )
        msg = deserialize(raw)
        assert isinstance(msg, PingMessage)

    def test_malformed_json_raises(self) -> None:
        with pytest.raises(ValidationError):
            deserialize('not-json')

    def test_unknown_type_raises(self) -> None:
        raw = json.dumps(
            {
                'type': 'unknown_xyz',
                'timestamp': datetime.now(UTC).isoformat(),
            }
        )
        with pytest.raises(ValidationError):
            deserialize(raw)


class TestFrameCodec:
    def test_encode_produces_frame_message(self, sample_frame: np.ndarray) -> None:
        msg = encode_frame(sample_frame, frame_id=5, quality=85)
        assert isinstance(msg, FrameMessage)
        assert msg.frame_id == 5
        assert msg.width == 640
        assert msg.height == 480
        assert len(msg.image_data) > 0

    def test_decode_recovers_compatible_frame(self, sample_frame: np.ndarray) -> None:
        msg = encode_frame(sample_frame, frame_id=3, quality=85)
        recovered, frame_id = decode_frame(msg)
        assert frame_id == 3
        assert recovered.shape == sample_frame.shape

    def test_encode_failure_raises(self) -> None:
        bad_frame = np.zeros((0, 0, 3), dtype=np.uint8)  # zero-dim array
        with pytest.raises(ValueError, match='JPEG encoding failed'):
            encode_frame(bad_frame, frame_id=1, quality=85)


class TestErrorAndPingPong:
    def test_make_error_without_frame_id(self) -> None:
        err = make_error('timeout', 'connection timed out')
        assert err.error_type == 'timeout'
        assert err.message == 'connection timed out'
        assert err.frame_id is None

    def test_make_error_with_frame_id(self) -> None:
        err = make_error('decode_error', 'bad jpeg', frame_id=7)
        assert err.frame_id == 7

    def test_make_pong_echoes_ping_timestamp(self) -> None:
        ping = PingMessage()
        pong = make_pong(ping)
        assert pong.ping_timestamp == ping.timestamp
