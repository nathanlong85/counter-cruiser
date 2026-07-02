"""Tests for LogHandler: structured alert-log append."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from counter_cruiser.client.alerts.context import AlertContext
from counter_cruiser.client.alerts.log import LogHandler
from counter_cruiser.config.models import LogConfig
from counter_cruiser.shared.protocol import BoundingBox


def _context() -> AlertContext:
    box = BoundingBox(
        x1=0, y1=0, x2=10, y2=10, confidence=0.9, class_id=16, class_name='dog'
    )
    return AlertContext(
        frame=None, detections=[box], zones=[], triggered_zones={'z1'}, frame_id=3
    )


class TestLogAppend:
    def test_record_includes_zones_frame_id_and_detection_count(
        self, tmp_path: Path
    ) -> None:
        log_path = tmp_path / 'alerts.log'
        handler = LogHandler(LogConfig(enabled=True, file=str(log_path)))
        handler.trigger(_context())
        lines = log_path.read_text().splitlines()
        assert len(lines) == 1
        record = json.loads(lines[0])
        assert record['triggered_zones'] == ['z1']
        assert record['frame_id'] == 3
        assert record['detection_count'] == 1

    def test_multiple_triggers_append(self, tmp_path: Path) -> None:
        log_path = tmp_path / 'alerts.log'
        handler = LogHandler(LogConfig(enabled=True, file=str(log_path)))
        handler.trigger(_context())
        handler.trigger(_context())
        assert len(log_path.read_text().splitlines()) == 2

    def test_write_failure_is_logged_and_does_not_raise(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        unwritable_dir = tmp_path / 'missing-parent' / 'alerts.log'
        handler = LogHandler(LogConfig(enabled=True, file=str(unwritable_dir)))
        with caplog.at_level('ERROR'):
            handler.trigger(_context())  # must not raise
        assert 'Failed to write alert log' in caplog.text


class TestLogCleanup:
    def test_cleanup_is_a_noop(self, tmp_path: Path) -> None:
        handler = LogHandler(LogConfig(enabled=True, file=str(tmp_path / 'a.log')))
        handler.cleanup()  # must not raise
