"""Typed WebSocket protocol models and codec utilities.

All messages carry a ``type`` literal for discriminated-union deserialization
and a UTC ``timestamp``. Frames are JPEG-encoded and base64-embedded in JSON.
"""

from __future__ import annotations

import base64
from datetime import UTC, datetime
from typing import Annotated, Literal

import cv2
import numpy as np
from pydantic import BaseModel, Field, TypeAdapter


def _utcnow() -> datetime:
    """Return the current UTC datetime."""
    return datetime.now(UTC)


# ---------------------------------------------------------------------------
# Shared sub-models
# ---------------------------------------------------------------------------


class BoundingBox(BaseModel):
    """A single object-detection result with pixel coordinates."""

    x1: int
    y1: int
    x2: int
    y2: int
    confidence: float
    class_id: int
    class_name: str


# ---------------------------------------------------------------------------
# Message models
# ---------------------------------------------------------------------------


class FrameMessage(BaseModel):
    """Client → server: a JPEG-encoded camera frame."""

    type: Literal['frame'] = 'frame'
    frame_id: int
    image_data: str  # base64-encoded JPEG bytes
    width: int
    height: int
    timestamp: datetime = Field(default_factory=_utcnow)


class DetectionMessage(BaseModel):
    """Server → client: inference results for one frame."""

    type: Literal['detection'] = 'detection'
    frame_id: int
    boxes: list[BoundingBox]
    processing_time_ms: float
    timestamp: datetime = Field(default_factory=_utcnow)


class ErrorMessage(BaseModel):
    """Server → client: a processing failure."""

    type: Literal['error'] = 'error'
    error_type: str
    message: str
    frame_id: int | None = None
    timestamp: datetime = Field(default_factory=_utcnow)


class PingMessage(BaseModel):
    """Either direction: connection health check."""

    type: Literal['ping'] = 'ping'
    timestamp: datetime = Field(default_factory=_utcnow)


class PongMessage(BaseModel):
    """Reply to a ping, echoing the ping timestamp."""

    type: Literal['pong'] = 'pong'
    ping_timestamp: datetime
    timestamp: datetime = Field(default_factory=_utcnow)


# ---------------------------------------------------------------------------
# Discriminated union + adapter (created once at import time)
# ---------------------------------------------------------------------------

AnyMessage = Annotated[
    FrameMessage | DetectionMessage | ErrorMessage | PingMessage | PongMessage,
    Field(discriminator='type'),
]

_ADAPTER: TypeAdapter[AnyMessage] = TypeAdapter(AnyMessage)

# ---------------------------------------------------------------------------
# Serialization
# ---------------------------------------------------------------------------


def serialize(
    msg: FrameMessage | DetectionMessage | ErrorMessage | PingMessage | PongMessage,
) -> str:
    """Serialize a message model to a JSON string."""
    return msg.model_dump_json()


def deserialize(data: str) -> AnyMessage:
    """Deserialize a JSON string to the correct typed message model.

    Raises ``pydantic.ValidationError`` for malformed payloads or unknown types.
    """
    return _ADAPTER.validate_json(data)


# ---------------------------------------------------------------------------
# Frame codec
# ---------------------------------------------------------------------------


def encode_frame(frame: np.ndarray, frame_id: int, quality: int = 85) -> FrameMessage:
    """JPEG-encode *frame* and pack it into a :class:`FrameMessage`.

    Raises ``ValueError`` if the encoder fails (e.g. zero-dimension array).
    """
    try:
        ok, buf = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, quality])
    except cv2.error as exc:
        raise ValueError(f'JPEG encoding failed for frame {frame_id}') from exc
    if not ok:  # pragma: no cover
        raise ValueError(f'JPEG encoding failed for frame {frame_id}')
    h, w = frame.shape[:2]
    image_data = base64.b64encode(buf.tobytes()).decode('ascii')
    return FrameMessage(frame_id=frame_id, image_data=image_data, width=w, height=h)


def decode_frame(msg: FrameMessage) -> tuple[np.ndarray, int]:
    """Decode a :class:`FrameMessage` back to a numpy BGR array.

    Returns ``(frame_array, frame_id)``.
    """
    buf = base64.b64decode(msg.image_data)
    arr = np.frombuffer(buf, dtype=np.uint8)
    frame = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    return frame, msg.frame_id


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_error(
    error_type: str, message: str, frame_id: int | None = None
) -> ErrorMessage:
    """Construct an :class:`ErrorMessage`."""
    return ErrorMessage(error_type=error_type, message=message, frame_id=frame_id)


def make_pong(ping: PingMessage) -> PongMessage:
    """Construct a :class:`PongMessage` echoing *ping*'s timestamp."""
    return PongMessage(ping_timestamp=ping.timestamp)
