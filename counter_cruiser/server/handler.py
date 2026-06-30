"""WebSocket connection handler for the inference server."""
from __future__ import annotations

import logging
import time

import websockets.exceptions

from counter_cruiser.server.model import DetectionModel
from counter_cruiser.shared.protocol import (
    DetectionMessage,
    FrameMessage,
    PingMessage,
    decode_frame,
    deserialize,
    make_error,
    make_pong,
    serialize,
)

logger = logging.getLogger(__name__)


async def handle_connection(websocket, model: DetectionModel) -> None:
    """Handle a single client connection; process frames until disconnect."""
    logger.info('Client connected: %s', websocket.remote_address)
    try:
        async for raw in websocket:
            msg = None
            try:
                msg = deserialize(raw)
                if isinstance(msg, PingMessage):
                    await websocket.send(serialize(make_pong(msg)))
                elif isinstance(msg, FrameMessage):
                    t0 = time.perf_counter()
                    frame, frame_id = decode_frame(msg)
                    boxes = model.detect(frame)
                    elapsed_ms = (time.perf_counter() - t0) * 1000.0
                    result = DetectionMessage(
                        frame_id=frame_id,
                        boxes=boxes,
                        processing_time_ms=elapsed_ms,
                    )
                    await websocket.send(serialize(result))
            except Exception as exc:
                logger.exception('Error processing message: %s', exc)
                frame_id = (
                    msg.frame_id if isinstance(msg, FrameMessage) else None
                )
                error_msg = make_error(
                    'processing_error', str(exc), frame_id
                )
                await websocket.send(serialize(error_msg))
    except websockets.exceptions.ConnectionClosed:
        logger.info('Client disconnected: %s', websocket.remote_address)
