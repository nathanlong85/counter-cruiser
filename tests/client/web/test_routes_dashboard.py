"""Tests for the status JSON endpoint."""

from __future__ import annotations

from counter_cruiser.client.web.app import create_app
from counter_cruiser.client.web.state import DashboardState
from counter_cruiser.config.models import ClientSettings
from counter_cruiser.shared.protocol import BoundingBox


class FakeZoneStore:
    def list_zones(self):
        return [], 0


def _client():
    state = DashboardState()
    app = create_app(state, ClientSettings(), FakeZoneStore())
    return app.test_client(), state


class TestStatusEndpoint:
    def test_returns_json_with_expected_keys(self) -> None:
        client, _ = _client()
        response = client.get('/api/status')
        assert response.status_code == 200
        body = response.get_json()
        assert set(body) == {
            'detection_state',
            'triggered_zones',
            'fps',
            'latency_ms',
            'server_connected',
        }

    def test_elevated_state_reported_with_triggered_zones(self) -> None:
        client, state = _client()
        box = BoundingBox(
            x1=1, y1=1, x2=2, y2=2, confidence=0.9, class_id=16, class_name='dog'
        )
        state.update_detection([box], {'z1', 'z2'}, elevated=True)
        body = client.get('/api/status').get_json()
        assert body['detection_state'] == 'elevated'
        assert sorted(body['triggered_zones']) == ['z1', 'z2']

    def test_floor_state_reported_with_no_triggered_zones(self) -> None:
        client, state = _client()
        state.update_detection([], set(), elevated=False)
        body = client.get('/api/status').get_json()
        assert body['detection_state'] == 'floor'
        assert body['triggered_zones'] == []

    def test_disconnected_server_is_reflected(self) -> None:
        client, state = _client()
        state.update_stats(fps=0.0, latency_ms=0.0, server_connected=False)
        body = client.get('/api/status').get_json()
        assert body['server_connected'] is False

    def test_fps_and_latency_are_reflected(self) -> None:
        client, state = _client()
        state.update_stats(fps=9.5, latency_ms=33.0, server_connected=True)
        body = client.get('/api/status').get_json()
        assert body['fps'] == 9.5
        assert body['latency_ms'] == 33.0
        assert body['server_connected'] is True
