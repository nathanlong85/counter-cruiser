"""Tests for the /api/deterrent-stats JSON endpoint."""

from __future__ import annotations

from counter_cruiser.client.web.app import create_app
from counter_cruiser.client.web.state import DashboardState
from counter_cruiser.config.models import ClientSettings


class FakeZoneStore:
    def list_zones(self):
        return [], 0


class FakeStatsStore:
    def __init__(self, events=None, failures=None):
        self._events = events or []
        self._failures = failures or []

    def recent_events(self, since_days: int):
        return self._events

    def recent_failures(self, limit: int):
        return self._failures[:limit]


def _client(state=None, stats_store=None):
    state = state or DashboardState()
    stats_store = stats_store or FakeStatsStore()
    app = create_app(state, ClientSettings(), FakeZoneStore(), stats_store)
    return app.test_client(), state, stats_store


class TestDeterrentStatsEndpoint:
    def test_returns_json_with_expected_keys(self) -> None:
        client, _, _ = _client()
        response = client.get('/api/deterrent-stats')
        assert response.status_code == 200
        body = response.get_json()
        assert set(body) == {'configured', 'operational', 'events', 'recent_failures'}

    def test_reflects_not_configured_status(self) -> None:
        client, state, _ = _client()
        state.set_deterrent_status(configured=False, operational=False)
        body = client.get('/api/deterrent-stats').get_json()
        assert body['configured'] is False
        assert body['operational'] is False

    def test_reflects_configured_and_operational_status(self) -> None:
        client, state, _ = _client()
        state.set_deterrent_status(configured=True, operational=True)
        body = client.get('/api/deterrent-stats').get_json()
        assert body['configured'] is True
        assert body['operational'] is True

    def test_events_are_serialized_from_the_store(self) -> None:
        stats_store = FakeStatsStore(
            events=[
                ('2026-01-01T00:00:00+00:00', True),
                ('2026-01-02T00:00:00+00:00', False),
            ]
        )
        client, _, _ = _client(stats_store=stats_store)
        body = client.get('/api/deterrent-stats').get_json()
        assert body['events'] == [
            {'timestamp_utc': '2026-01-01T00:00:00+00:00', 'succeeded': True},
            {'timestamp_utc': '2026-01-02T00:00:00+00:00', 'succeeded': False},
        ]

    def test_no_events_returns_empty_list(self) -> None:
        client, _, _ = _client()
        body = client.get('/api/deterrent-stats').get_json()
        assert body['events'] == []

    def test_recent_failures_are_included(self) -> None:
        stats_store = FakeStatsStore(failures=['2026-01-02T00:00:00+00:00'])
        client, _, _ = _client(stats_store=stats_store)
        body = client.get('/api/deterrent-stats').get_json()
        assert body['recent_failures'] == ['2026-01-02T00:00:00+00:00']


class TestTrainingProgressPage:
    def test_page_is_served(self) -> None:
        client, _, _ = _client()
        response = client.get('/training-progress')
        assert response.status_code == 200
        assert b'<html' in response.data

    def test_page_renders_with_no_events_yet(self) -> None:
        """The page must serve successfully even with zero recorded events —
        the no-events-yet state is handled by the page's own JS, not the
        server, but the route itself must never error on an empty store."""
        stats_store = FakeStatsStore(events=[], failures=[])
        client, _, _ = _client(stats_store=stats_store)
        response = client.get('/training-progress')
        assert response.status_code == 200
