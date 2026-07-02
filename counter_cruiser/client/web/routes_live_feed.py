"""Live MJPEG feed route."""

from __future__ import annotations

from flask import Flask, Response

from counter_cruiser.client.web.mjpeg import generate_mjpeg_stream
from counter_cruiser.client.web.state import DashboardState
from counter_cruiser.config.models import ClientSettings


def register_live_feed_routes(
    app: Flask, state: DashboardState, settings: ClientSettings
) -> None:
    """Register the MJPEG streaming endpoint on *app*."""

    @app.get('/video_feed')
    def live_feed():
        return Response(
            generate_mjpeg_stream(state, settings),
            mimetype='multipart/x-mixed-replace; boundary=frame',
        )
