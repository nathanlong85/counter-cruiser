"""Client entrypoint: wire config, camera, transport, zone analysis, and debounce."""

from __future__ import annotations

import asyncio
import logging
import signal

from counter_cruiser.client.capture import OpenCVCapture
from counter_cruiser.client.transport import ClientSession
from counter_cruiser.config.loader import load_client_config
from counter_cruiser.shared.debounce import DetectionHistory
from counter_cruiser.shared.geometry import analyze_detections
from counter_cruiser.shared.protocol import DetectionMessage

logger = logging.getLogger(__name__)


def _configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s %(name)s %(levelname)s %(message)s',
    )


def main() -> None:
    """Load configuration and run the client until interrupted."""
    _configure_logging()
    config = load_client_config()
    history = DetectionHistory()

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

    session = ClientSession(capture=OpenCVCapture(), config=config, on_result=on_result)

    def _shutdown(signum, frame):  # pragma: no cover
        logger.info('Shutdown signal received')
        session.stop()

    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    asyncio.run(session.run())


if __name__ == '__main__':  # pragma: no cover
    main()
