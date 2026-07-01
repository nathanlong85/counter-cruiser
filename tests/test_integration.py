"""Integration tests: fake camera + in-process WebSocket + fake model -> report."""

from __future__ import annotations

import asyncio

import numpy as np
import pytest
import websockets

from counter_cruiser.client.transport import ClientSession
from counter_cruiser.config.models import ClientSettings, Zone
from counter_cruiser.server.handler import handle_connection
from counter_cruiser.server.model import DetectionModel
from counter_cruiser.shared.debounce import DetectionHistory
from counter_cruiser.shared.geometry import analyze_detections
from counter_cruiser.shared.protocol import BoundingBox, DetectionMessage


class _FakeCapture:
    """Yields *frames* in order; returns None once exhausted."""

    def __init__(self, frames: list[np.ndarray]) -> None:
        """Store the frames to be replayed in order."""
        self._frames = list(frames)
        self._idx = 0
        self.released = False

    def open(self, index: int, width: int, height: int) -> tuple[int, int]:
        """Pretend to open the camera; always report 640x480."""
        return (640, 480)

    def read(self) -> np.ndarray | None:
        """Return the next stored frame, or None once exhausted."""
        if self._idx >= len(self._frames):
            return None
        frame = self._frames[self._idx]
        self._idx += 1
        return frame

    def release(self) -> None:
        """Mark the capture as released."""
        self.released = True


class _FakeModel(DetectionModel):
    """Returns a fixed set of boxes regardless of the input frame."""

    def __init__(self, boxes: list[BoundingBox]) -> None:
        """Store the boxes to return for every detect() call."""
        self._boxes = boxes

    def detect(self, frame: np.ndarray) -> list[BoundingBox]:
        """Ignore the frame and return the fixed boxes."""
        return self._boxes


@pytest.mark.integration
async def test_elevated_dog_reported_elevated() -> None:
    """A large dog inside the zone is reported ELEVATED after two detections."""
    zone = Zone(
        id='counter',
        name='Counter',
        polygon=[(0, 0), (640, 0), (640, 480), (0, 480)],
    )
    # height=300, frame_height=480 -> ratio≈0.625 > min_size_ratio=0.25
    elevated_box = BoundingBox(
        x1=0, y1=0, x2=100, y2=300, confidence=0.9, class_id=16, class_name='dog'
    )
    frames = [np.zeros((480, 640, 3), dtype=np.uint8)] * 4

    received: list[tuple[DetectionMessage, float]] = []
    history = DetectionHistory()
    statuses: list[str] = []
    zones = [zone]
    min_size_ratio = 0.25

    def on_result(msg: DetectionMessage, latency: float) -> None:
        received.append((msg, latency))
        analysis = analyze_detections(msg.boxes, zones, 480, min_size_ratio)
        history.add(msg.frame_id, analysis.elevated)
        statuses.append('ELEVATED' if history.is_consecutive_elevated() else 'floor')

    async with websockets.serve(
        lambda ws: handle_connection(ws, _FakeModel([elevated_box])),
        'localhost',
        0,
    ) as server:
        port = server.sockets[0].getsockname()[1]
        config = ClientSettings(
            server_host='localhost',
            server_port=port,
            zones=zones,
            min_size_ratio=min_size_ratio,
            frame_skip=1,
            jpeg_quality=85,
        )
        capture = _FakeCapture(frames)
        session = ClientSession(
            capture=capture, config=config, on_result=on_result, reconnect_interval=0.1
        )

        task = asyncio.create_task(session.run())
        deadline = asyncio.get_event_loop().time() + 5.0
        while len(received) < 2 and asyncio.get_event_loop().time() < deadline:
            await asyncio.sleep(0.02)
        session.stop()
        await asyncio.wait_for(task, timeout=3.0)

    assert len(received) >= 2
    assert received[0][0].boxes[0].class_name == 'dog'
    # Two consecutive elevated detections should debounce to an ELEVATED report.
    assert 'ELEVATED' in statuses


@pytest.mark.integration
async def test_floor_dog_reported_not_elevated() -> None:
    """A small dog below min_size_ratio is always reported floor (not elevated)."""
    zone = Zone(
        id='counter',
        name='Counter',
        polygon=[(0, 0), (640, 0), (640, 480), (0, 480)],
    )
    # height=50, frame_height=480 -> ratio≈0.10 < min_size_ratio=0.25
    floor_box = BoundingBox(
        x1=0, y1=0, x2=100, y2=50, confidence=0.9, class_id=16, class_name='dog'
    )
    frames = [np.zeros((480, 640, 3), dtype=np.uint8)] * 3

    received: list[tuple[DetectionMessage, float]] = []
    history = DetectionHistory()
    statuses: list[str] = []
    zones = [zone]
    min_size_ratio = 0.25

    def on_result(msg: DetectionMessage, latency: float) -> None:
        received.append((msg, latency))
        analysis = analyze_detections(msg.boxes, zones, 480, min_size_ratio)
        history.add(msg.frame_id, analysis.elevated)
        statuses.append('ELEVATED' if history.is_consecutive_elevated() else 'floor')

    async with websockets.serve(
        lambda ws: handle_connection(ws, _FakeModel([floor_box])),
        'localhost',
        0,
    ) as server:
        port = server.sockets[0].getsockname()[1]
        config = ClientSettings(
            server_host='localhost',
            server_port=port,
            zones=zones,
            min_size_ratio=min_size_ratio,
            frame_skip=1,
            jpeg_quality=85,
        )
        capture = _FakeCapture(frames)
        session = ClientSession(
            capture=capture, config=config, on_result=on_result, reconnect_interval=0.1
        )

        task = asyncio.create_task(session.run())
        deadline = asyncio.get_event_loop().time() + 5.0
        while len(received) < 2 and asyncio.get_event_loop().time() < deadline:
            await asyncio.sleep(0.02)
        session.stop()
        await asyncio.wait_for(task, timeout=3.0)

    assert len(received) >= 1
    assert 'ELEVATED' not in statuses
    assert all(status == 'floor' for status in statuses)
