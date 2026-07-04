"""Deterrent usage-stats JSON endpoint: recent events + operational status."""

from __future__ import annotations

from typing import Protocol

from flask import Flask, jsonify

from counter_cruiser.client.web.state import DashboardState

_SINCE_DAYS = 182
_FAILURE_LIMIT = 50


class DeterrentStatsStoreProtocol(Protocol):
    """Structural interface the route depends on for stats retrieval."""

    def recent_events(self, since_days: int) -> list[tuple[str, bool]]:
        """Return (timestamp_utc, succeeded) pairs within since_days."""
        ...  # pragma: no cover

    def recent_failures(self, limit: int) -> list[str]:
        """Return up to limit most recent failed-event timestamps."""
        ...  # pragma: no cover


def register_deterrent_stats_routes(
    app: Flask, state: DashboardState, stats_store: DeterrentStatsStoreProtocol
) -> None:
    """Register the deterrent usage-stats JSON endpoint on *app*."""

    @app.get('/api/deterrent-stats')
    def deterrent_stats():
        status = state.get_deterrent_status()
        events = stats_store.recent_events(since_days=_SINCE_DAYS)
        failures = stats_store.recent_failures(limit=_FAILURE_LIMIT)
        return jsonify(
            {
                'configured': status.configured,
                'operational': status.operational,
                'events': [{'timestamp_utc': ts, 'succeeded': ok} for ts, ok in events],
                'recent_failures': failures,
            }
        )
