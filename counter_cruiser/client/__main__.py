"""Client entrypoint: wire config, camera, transport, zone analysis, alerts."""

from __future__ import annotations

import asyncio
import logging
import signal
import threading
import time
from collections import deque
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from werkzeug.serving import make_server

from counter_cruiser.client.alerts.context import AlertContext
from counter_cruiser.client.alerts.deterrent import DeterrentHandler
from counter_cruiser.client.alerts.log import LogHandler
from counter_cruiser.client.alerts.manager import AlertManager
from counter_cruiser.client.alerts.notifications import NotificationHandler
from counter_cruiser.client.alerts.snapshot import SnapshotHandler
from counter_cruiser.client.capture import OpenCVCapture
from counter_cruiser.client.deterrent_stats import DeterrentStatsStore
from counter_cruiser.client.transport import ClientSession
from counter_cruiser.client.web.app import create_app
from counter_cruiser.client.web.state import AlertHistoryEntry, DashboardState
from counter_cruiser.client.web.zone_store import ZoneStore
from counter_cruiser.config.loader import load_client_config, resolve_client_config_path
from counter_cruiser.config.models import ClientSettings
from counter_cruiser.shared.debounce import DetectionHistory
from counter_cruiser.shared.geometry import analyze_detections
from counter_cruiser.shared.protocol import DetectionMessage

logger = logging.getLogger(__name__)

_FPS_WINDOW_SECONDS = 5.0


def _configure_logging() -> None:
    """Configure root logging: INFO level with a timestamped format."""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s %(name)s %(levelname)s %(message)s',
    )


def _run_web_server(app, host: str, port: int) -> None:
    """Serve *app* forever on (host, port) via werkzeug's dev server.

    ``threaded=True`` is required: the dashboard embeds ``/video_feed``, an
    infinite MJPEG generator that only returns when the client disconnects,
    alongside ``/api/status``/``/api/alerts`` polling. A single-threaded
    server (werkzeug's default) would let the stream connection permanently
    starve every other endpoint.
    """
    make_server(host, port, app, threaded=True).serve_forever()


class _FpsTracker:
    """Rolling-window FPS estimate from on_result call timestamps."""

    def __init__(
        self,
        window_seconds: float = _FPS_WINDOW_SECONDS,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        """Track arrivals over a rolling *window_seconds* using the injected *clock*."""
        self._window_seconds = window_seconds
        self._clock = clock
        self._timestamps: deque[float] = deque()

    def tick(self) -> float:
        """Record one arrival now; return the current windowed FPS estimate."""
        now = self._clock()
        self._timestamps.append(now)
        cutoff = now - self._window_seconds
        while self._timestamps and self._timestamps[0] < cutoff:
            self._timestamps.popleft()
        if len(self._timestamps) < 2:
            return 0.0
        span = self._timestamps[-1] - self._timestamps[0]
        return (len(self._timestamps) - 1) / span if span > 0 else 0.0


def _build_alert_manager(
    config: ClientSettings, stats_store: DeterrentStatsStore
) -> tuple[AlertManager, DeterrentHandler | None]:
    """Construct the AlertManager from enabled handlers in *config*.

    Returns the manager alongside the constructed DeterrentHandler (or None
    if disabled) so callers can read its operational status without
    reaching into the manager's internals.
    """
    alerts = config.alerts
    deterrent = (
        DeterrentHandler(alerts.deterrent, stats_store)
        if alerts.deterrent.enabled
        else None
    )
    handlers = []
    if alerts.snapshot.enabled:
        handlers.append(SnapshotHandler(alerts.snapshot))
    if alerts.log.enabled:
        handlers.append(LogHandler(alerts.log))
    if alerts.notification.enabled:
        handlers.append(NotificationHandler(alerts.notification))
    manager = AlertManager(
        handlers=handlers, cooldown_seconds=alerts.cooldown_seconds, deterrent=deterrent
    )
    return manager, deterrent


def main() -> None:
    """Load configuration and run the client until interrupted."""
    _configure_logging()
    config = load_client_config()
    history = DetectionHistory()
    stats_store = DeterrentStatsStore(Path(config.alerts.deterrent.stats_db_path))
    alert_manager, deterrent_handler = _build_alert_manager(config, stats_store)

    dashboard_state = DashboardState()
    dashboard_state.set_deterrent_status(
        configured=config.alerts.deterrent.enabled,
        operational=deterrent_handler.is_operational if deterrent_handler else False,
    )
    zone_store = ZoneStore(config, resolve_client_config_path())
    fps_tracker = _FpsTracker()
    web_app = create_app(dashboard_state, config, zone_store, stats_store)
    web_thread = threading.Thread(
        target=_run_web_server,
        args=(web_app, config.web_host, config.web_port),
        daemon=True,
    )
    web_thread.start()

    def on_result(msg: DetectionMessage, latency: float) -> None:
        zones, _ = zone_store.list_zones()
        analysis = analyze_detections(
            msg.boxes, zones, session.frame_height, config.min_size_ratio
        )
        history.add(msg.frame_id, analysis.elevated)
        actionable = history.is_consecutive_elevated()
        status = 'ELEVATED' if actionable else 'floor'
        triggered = (
            ', '.join(sorted(analysis.triggered_zones))
            if analysis.triggered_zones
            else 'none'
        )
        logger.info(
            'frame=%d latency=%.1fms status=%s zones=[%s]',
            msg.frame_id,
            latency * 1000.0,
            status,
            triggered,
        )
        frame = session.get_frame(msg.frame_id)
        if frame is not None:
            dashboard_state.update_frame(frame)
        dashboard_state.update_detection(
            msg.boxes, analysis.triggered_zones, actionable
        )
        fps = fps_tracker.tick()
        dashboard_state.update_stats(
            fps=fps, latency_ms=latency * 1000.0, server_connected=True
        )
        if actionable:
            context = AlertContext(
                frame=session.get_frame(msg.frame_id),
                detections=msg.boxes,
                zones=zones,
                triggered_zones=analysis.triggered_zones,
                frame_id=msg.frame_id,
            )
            alert_manager.maybe_alert(context)
            dashboard_state.record_alert(
                AlertHistoryEntry(
                    time=datetime.now(UTC),
                    triggered_zones=frozenset(analysis.triggered_zones),
                    frame_id=msg.frame_id,
                )
            )

    session = ClientSession(
        capture=OpenCVCapture(),
        config=config,
        on_result=on_result,
        on_connection_change=dashboard_state.set_server_connected,
    )

    def _shutdown(signum, frame):  # pragma: no cover
        logger.info('Shutdown signal received')
        session.stop()

    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    try:
        asyncio.run(session.run())
    finally:
        alert_manager.cleanup()


if __name__ == '__main__':  # pragma: no cover
    main()
