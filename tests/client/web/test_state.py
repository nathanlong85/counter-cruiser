"""Tests for DashboardState: thread-safe injected UI state."""

from __future__ import annotations

from datetime import UTC, datetime

import numpy as np

from counter_cruiser.client.web.state import AlertHistoryEntry, DashboardState, DeterrentStatus
from counter_cruiser.shared.protocol import BoundingBox


def _box() -> BoundingBox:
    return BoundingBox(
        x1=1, y1=1, x2=2, y2=2, confidence=0.9, class_id=16, class_name='dog'
    )


class TestFrame:
    def test_no_frame_yet_returns_none(self) -> None:
        state = DashboardState()
        assert state.get_frame() is None

    def test_update_and_get_frame_round_trips(self) -> None:
        state = DashboardState()
        frame = np.ones((4, 4, 3), dtype=np.uint8)
        state.update_frame(frame)
        result = state.get_frame()
        assert result is not None
        np.testing.assert_array_equal(result, frame)

    def test_get_frame_is_copy_on_read(self) -> None:
        state = DashboardState()
        frame = np.zeros((2, 2, 3), dtype=np.uint8)
        state.update_frame(frame)
        result = state.get_frame()
        assert result is not None
        result[0, 0, 0] = 255
        np.testing.assert_array_equal(state.get_frame(), frame)


class TestDetection:
    def test_default_detection_is_floor_with_no_zones(self) -> None:
        state = DashboardState()
        snapshot = state.get_detection()
        assert snapshot.elevated is False
        assert snapshot.triggered_zones == set()
        assert snapshot.detections == []

    def test_update_detection_round_trips(self) -> None:
        state = DashboardState()
        state.update_detection([_box()], {'z1'}, True)
        snapshot = state.get_detection()
        assert snapshot.elevated is True
        assert snapshot.triggered_zones == {'z1'}
        assert snapshot.detections == [_box()]


class TestStats:
    def test_default_stats_are_zeroed_and_disconnected(self) -> None:
        state = DashboardState()
        stats = state.get_stats()
        assert stats.fps == 0.0
        assert stats.latency_ms == 0.0
        assert stats.server_connected is False

    def test_update_stats_round_trips(self) -> None:
        state = DashboardState()
        state.update_stats(fps=12.5, latency_ms=42.0, server_connected=True)
        stats = state.get_stats()
        assert stats.fps == 12.5
        assert stats.latency_ms == 42.0
        assert stats.server_connected is True

    def test_set_server_connected_preserves_fps_and_latency(self) -> None:
        state = DashboardState()
        state.update_stats(fps=12.5, latency_ms=42.0, server_connected=True)
        state.set_server_connected(False)
        stats = state.get_stats()
        assert stats.fps == 12.5
        assert stats.latency_ms == 42.0
        assert stats.server_connected is False

    def test_set_server_connected_true_from_default(self) -> None:
        state = DashboardState()
        state.set_server_connected(True)
        stats = state.get_stats()
        assert stats.server_connected is True
        assert stats.fps == 0.0
        assert stats.latency_ms == 0.0


class TestAlertHistory:
    def test_no_alerts_returns_empty_list(self) -> None:
        state = DashboardState()
        assert state.get_alerts() == []

    def test_alerts_are_returned_newest_first(self) -> None:
        state = DashboardState()
        first = AlertHistoryEntry(
            time=datetime(2026, 1, 1, tzinfo=UTC),
            triggered_zones=frozenset({'z1'}),
            frame_id=1,
        )
        second = AlertHistoryEntry(
            time=datetime(2026, 1, 2, tzinfo=UTC),
            triggered_zones=frozenset({'z2'}),
            frame_id=2,
        )
        state.record_alert(first)
        state.record_alert(second)
        assert state.get_alerts() == [second, first]

    def test_alert_history_is_bounded(self) -> None:
        state = DashboardState(alert_history_capacity=2)
        for i in range(3):
            state.record_alert(
                AlertHistoryEntry(
                    time=datetime(2026, 1, 1, tzinfo=UTC),
                    triggered_zones=frozenset(),
                    frame_id=i,
                )
            )
        alerts = state.get_alerts()
        assert len(alerts) == 2
        assert [a.frame_id for a in alerts] == [2, 1]


class TestDeterrentStatus:
    def test_default_status_is_not_configured_not_operational(self) -> None:
        state = DashboardState()
        status = state.get_deterrent_status()
        assert status.configured is False
        assert status.operational is False

    def test_set_and_get_round_trips(self) -> None:
        state = DashboardState()
        state.set_deterrent_status(configured=True, operational=True)
        status = state.get_deterrent_status()
        assert status.configured is True
        assert status.operational is True

    def test_configured_but_not_operational(self) -> None:
        state = DashboardState()
        state.set_deterrent_status(configured=True, operational=False)
        status = state.get_deterrent_status()
        assert status.configured is True
        assert status.operational is False
