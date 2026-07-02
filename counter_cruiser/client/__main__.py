"""Client entrypoint: wire config, camera, transport, zone analysis, alerts."""

from __future__ import annotations

import asyncio
import logging
import signal

from counter_cruiser.client.alerts.context import AlertContext
from counter_cruiser.client.alerts.deterrent import DeterrentHandler
from counter_cruiser.client.alerts.log import LogHandler
from counter_cruiser.client.alerts.manager import AlertManager
from counter_cruiser.client.alerts.notifications import NotificationHandler
from counter_cruiser.client.alerts.snapshot import SnapshotHandler
from counter_cruiser.client.capture import OpenCVCapture
from counter_cruiser.client.transport import ClientSession
from counter_cruiser.config.loader import load_client_config
from counter_cruiser.config.models import ClientSettings
from counter_cruiser.shared.debounce import DetectionHistory
from counter_cruiser.shared.geometry import analyze_detections
from counter_cruiser.shared.protocol import DetectionMessage

logger = logging.getLogger(__name__)


def _configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s %(name)s %(levelname)s %(message)s',
    )


def _build_alert_manager(config: ClientSettings) -> AlertManager:
    """Construct the AlertManager from enabled handlers in *config*."""
    alerts = config.alerts
    deterrent = DeterrentHandler(alerts.deterrent) if alerts.deterrent.enabled else None
    handlers = []
    if alerts.snapshot.enabled:
        handlers.append(SnapshotHandler(alerts.snapshot))
    if alerts.log.enabled:
        handlers.append(LogHandler(alerts.log))
    if alerts.notification.enabled:
        handlers.append(NotificationHandler(alerts.notification))
    return AlertManager(
        handlers=handlers, cooldown_seconds=alerts.cooldown_seconds, deterrent=deterrent
    )


def main() -> None:
    """Load configuration and run the client until interrupted."""
    _configure_logging()
    config = load_client_config()
    history = DetectionHistory()
    alert_manager = _build_alert_manager(config)

    def on_result(msg: DetectionMessage, latency: float) -> None:
        analysis = analyze_detections(
            msg.boxes, config.zones, session.frame_height, config.min_size_ratio
        )
        history.add(msg.frame_id, analysis.elevated)
        actionable = history.is_consecutive_elevated()
        status = 'ELEVATED' if actionable else 'floor'
        zones = (
            ', '.join(sorted(analysis.triggered_zones))
            if analysis.triggered_zones
            else 'none'
        )
        logger.info(
            'frame=%d latency=%.1fms status=%s zones=[%s]',
            msg.frame_id,
            latency * 1000.0,
            status,
            zones,
        )
        if actionable:
            context = AlertContext(
                frame=session.get_frame(msg.frame_id),
                detections=msg.boxes,
                zones=config.zones,
                triggered_zones=analysis.triggered_zones,
                frame_id=msg.frame_id,
            )
            alert_manager.maybe_alert(context)

    session = ClientSession(capture=OpenCVCapture(), config=config, on_result=on_result)

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
