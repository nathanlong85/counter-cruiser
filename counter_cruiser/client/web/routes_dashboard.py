"""Status and alert-history routes: read-only views over DashboardState."""

from __future__ import annotations

from flask import Flask, jsonify

from counter_cruiser.client.web.state import DashboardState


def register_dashboard_routes(app: Flask, state: DashboardState) -> None:
    """Register the status JSON endpoint on *app*."""

    @app.get('/api/status')
    def status():
        detection = state.get_detection()
        stats = state.get_stats()
        return jsonify(
            {
                'detection_state': 'elevated' if detection.elevated else 'floor',
                'triggered_zones': sorted(detection.triggered_zones),
                'fps': stats.fps,
                'latency_ms': stats.latency_ms,
                'server_connected': stats.server_connected,
            }
        )

    @app.get('/api/alerts')
    def alerts():
        return jsonify(
            [
                {
                    'time': entry.time.isoformat(),
                    'triggered_zones': sorted(entry.triggered_zones),
                    'frame_id': entry.frame_id,
                }
                for entry in state.get_alerts()
            ]
        )
