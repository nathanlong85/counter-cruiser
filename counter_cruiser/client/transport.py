"""WebSocket client session: send frames, receive detections, reconnect on drop."""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Callable

import websockets
import websockets.exceptions

from counter_cruiser.client.capture import CameraCapture
from counter_cruiser.config.models import ClientSettings
from counter_cruiser.shared.protocol import (
    DetectionMessage,
    ErrorMessage,
    deserialize,
    encode_frame,
    serialize,
)

logger = logging.getLogger(__name__)


class ClientSession:
    """Manages the camera→server→zone-analysis pipeline with auto-reconnect.

    Constructs with injected dependencies so every part is testable headlessly.
    """

    def __init__(
        self,
        capture: CameraCapture,
        config: ClientSettings,
        on_result: Callable[[DetectionMessage, float], None],
        reconnect_interval: float = 5.0,
    ) -> None:
        """Initialise the session without opening any resources."""
        self._capture = capture
        self._config = config
        self._on_result = on_result
        self._reconnect_interval = reconnect_interval
        self._running = True
        self._pending: dict[int, float] = {}
        self._frame_id = 0
        self._frame_height = config.frame_height

    @property
    def _url(self) -> str:
        return f'ws://{self._config.server_host}:{self._config.server_port}'

    @property
    def frame_height(self) -> int:
        """Return the camera's actual negotiated frame height.

        Falls back to the configured value until the camera is opened.
        """
        return self._frame_height

    async def run(self) -> None:
        """Open the camera, connect to the server, and run until stopped."""
        _, actual_height = self._capture.open(
            self._config.camera_index,
            self._config.frame_width,
            self._config.frame_height,
        )
        self._frame_height = actual_height
        try:
            while self._running:
                try:
                    ws = await websockets.connect(self._url)
                    async with ws:
                        await self._run_connection(ws)
                except (OSError, websockets.exceptions.WebSocketException) as exc:
                    if not self._running:
                        break
                    logger.warning(
                        'Connection to %s failed: %s — retrying in %.1fs',
                        self._url,
                        exc,
                        self._reconnect_interval,
                    )
                    await asyncio.sleep(self._reconnect_interval)
        finally:
            self._capture.release()

    async def _run_connection(self, ws) -> None:
        """Run send and receive loops concurrently; raise on first exception."""
        self._pending.clear()
        send_task = asyncio.create_task(self._send_loop(ws))
        recv_task = asyncio.create_task(self._receive_loop(ws))
        try:
            await asyncio.gather(send_task, recv_task)
        except Exception:
            send_task.cancel()
            recv_task.cancel()
            await asyncio.gather(send_task, recv_task, return_exceptions=True)
            raise

    async def _send_loop(self, ws) -> None:
        """Capture frames (respecting frame_skip) and send them encoded."""
        skip = self._config.frame_skip
        count = 0
        while self._running:
            frame = self._capture.read()
            if frame is None:
                logger.warning('Frame read returned None; skipping')
                await asyncio.sleep(0.01)
                continue
            count += 1
            if count % skip != 0:
                continue
            self._frame_id += 1
            msg = encode_frame(frame, self._frame_id, self._config.jpeg_quality)
            self._pending[self._frame_id] = time.monotonic()
            await ws.send(serialize(msg))
        await ws.close()

    async def _receive_loop(self, ws) -> None:
        """Receive detections and errors; match detections to sent frames."""
        async for raw in ws:
            msg = deserialize(raw)
            if isinstance(msg, DetectionMessage):
                sent_at = self._pending.pop(msg.frame_id, None)
                latency = (time.monotonic() - sent_at) if sent_at is not None else 0.0
                self._on_result(msg, latency)
            elif isinstance(msg, ErrorMessage):
                logger.error(
                    'Server error [%s]: %s (frame=%s)',
                    msg.error_type,
                    msg.message,
                    msg.frame_id,
                )

    def stop(self) -> None:
        """Signal the session to stop sending and exit after the current frame."""
        self._running = False
