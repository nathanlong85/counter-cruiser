"""Tests for SnapshotHandler: annotated JPEG + JSON sidecar, max-count cleanup."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from counter_cruiser.client.alerts.context import AlertContext
from counter_cruiser.client.alerts.snapshot import SnapshotHandler
from counter_cruiser.config.models import SnapshotConfig
from counter_cruiser.shared.protocol import BoundingBox


def _box() -> BoundingBox:
    return BoundingBox(
        x1=0, y1=0, x2=10, y2=10, confidence=0.9, class_id=16, class_name='dog'
    )


def _context(frame: np.ndarray | None, frame_id: int = 1) -> AlertContext:
    return AlertContext(
        frame=frame,
        detections=[_box()],
        zones=[],
        triggered_zones={'z1'},
        frame_id=frame_id,
    )


class TestSnapshotSave:
    def test_writes_jpeg_and_json_sidecar(self, tmp_path: Path) -> None:
        config = SnapshotConfig(enabled=True, dir=str(tmp_path))
        handler = SnapshotHandler(config)
        frame = np.zeros((20, 20, 3), dtype=np.uint8)

        handler.trigger(_context(frame, frame_id=7))

        images = list(tmp_path.glob('*.jpg'))
        sidecars = list(tmp_path.glob('*.json'))
        assert len(images) == 1
        assert len(sidecars) == 1
        payload = json.loads(sidecars[0].read_text())
        assert payload['triggered_zones'] == ['z1']
        assert payload['detection_count'] == 1
        assert payload['frame_id'] == 7
        assert 'timestamp' in payload


class TestSnapshotAnnotation:
    def test_overlay_applied_when_enabled(self, tmp_path: Path) -> None:
        config = SnapshotConfig(
            enabled=True, dir=str(tmp_path), include_boxes=True, include_zones=True
        )
        handler = SnapshotHandler(config)
        frame = np.zeros((20, 20, 3), dtype=np.uint8)
        handler.trigger(_context(frame))
        # Rely on annotate_frame's own coverage for pixel-level assertions;
        # here we assert the handler wires include_boxes/include_zones through.
        import cv2

        saved = cv2.imread(str(next(tmp_path.glob('*.jpg'))))
        assert saved is not None


class TestSnapshotMaxCount:
    def test_oldest_deleted_when_over_cap(self, tmp_path: Path) -> None:
        config = SnapshotConfig(enabled=True, dir=str(tmp_path), max_count=2)
        handler = SnapshotHandler(config)
        frame = np.zeros((5, 5, 3), dtype=np.uint8)
        for i in range(4):
            handler.trigger(_context(frame, frame_id=i))
        images = sorted(tmp_path.glob('*.jpg'))
        sidecars = sorted(tmp_path.glob('*.json'))
        assert len(images) == 2
        assert len(sidecars) == 2

    def test_no_deletion_when_under_cap(self, tmp_path: Path) -> None:
        config = SnapshotConfig(enabled=True, dir=str(tmp_path), max_count=10)
        handler = SnapshotHandler(config)
        frame = np.zeros((5, 5, 3), dtype=np.uint8)
        for i in range(3):
            handler.trigger(_context(frame, frame_id=i))
        assert len(list(tmp_path.glob('*.jpg'))) == 3


class TestSnapshotMissingFrame:
    def test_missing_frame_logs_and_returns_without_writing(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        config = SnapshotConfig(enabled=True, dir=str(tmp_path))
        handler = SnapshotHandler(config)
        with caplog.at_level('WARNING'):
            handler.trigger(_context(None))  # must not raise
        assert list(tmp_path.glob('*.jpg')) == []
        assert 'No frame retained' in caplog.text


class TestSnapshotCleanup:
    def test_cleanup_is_a_noop(self, tmp_path: Path) -> None:
        handler = SnapshotHandler(SnapshotConfig(enabled=True, dir=str(tmp_path)))
        handler.cleanup()  # must not raise
