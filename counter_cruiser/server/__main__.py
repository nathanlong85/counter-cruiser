"""Server entrypoint: load config, model, and start the WebSocket server."""
from __future__ import annotations

import asyncio
import logging

import websockets

from counter_cruiser.config.loader import load_server_config
from counter_cruiser.server.handler import handle_connection
from counter_cruiser.server.model import YOLOAdapter, select_device

logger = logging.getLogger(__name__)


def _configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s %(name)s %(levelname)s %(message)s',
    )


async def _serve() -> None:
    """Load config and model, then serve indefinitely."""
    config = load_server_config()
    device = select_device(config.device)
    logger.info('Loading model %s on device %s', config.model_name, device)
    model = YOLOAdapter(config.model_name, device, config.confidence_threshold)
    logger.info('Server listening on %s:%d', config.host, config.port)
    async with websockets.serve(
        lambda ws: handle_connection(ws, model),
        config.host,
        config.port,
    ):
        await asyncio.Future()  # run until cancelled  # pragma: no cover


def main() -> None:
    """Configure logging and run the server."""
    _configure_logging()
    asyncio.run(_serve())


if __name__ == '__main__':  # pragma: no cover
    main()
