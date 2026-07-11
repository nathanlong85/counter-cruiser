"""Tests for the live-feed streaming endpoint."""

from __future__ import annotations

from counter_cruiser.client.web.app import create_app
from counter_cruiser.client.web.state import DashboardState
from counter_cruiser.config.models import ClientSettings


class FakeZoneStore:
    def list_zones(self):
        return [], 0


class FakeStatsStore:
    def recent_events(self, since_days: int):
        return []

    def recent_failures(self, limit: int):
        return []


def test_video_feed_returns_multipart_mimetype() -> None:
    app = create_app(
        DashboardState(), ClientSettings(), FakeZoneStore(), FakeStatsStore()
    )
    client = app.test_client()
    response = client.get('/video_feed')
    assert response.status_code == 200
    assert response.mimetype == 'multipart/x-mixed-replace'
    response.close()


def test_video_feed_endpoint_is_named_live_feed() -> None:
    app = create_app(
        DashboardState(), ClientSettings(), FakeZoneStore(), FakeStatsStore()
    )
    with app.test_request_context():
        from flask import url_for

        assert url_for('live_feed') == '/video_feed'
