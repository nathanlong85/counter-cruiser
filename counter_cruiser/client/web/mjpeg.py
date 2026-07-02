"""MJPEG stream generator: rate-limited, placeholder-before-first-frame.

Uses an injectable clock/sleep pair so tests bound iteration count and
elapsed time deterministically, per the design doc's testing strategy.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Iterator
from functools import lru_cache
from typing import Protocol

import cv2
import numpy as np

from counter_cruiser.client.annotation import annotate_frame
from counter_cruiser.client.web.state import DashboardState
from counter_cruiser.config.models import ClientSettings, Zone

_BOUNDARY = b'--frame'
_PLACEHOLDER_SIZE = (480, 640, 3)
_PLACEHOLDER_TEXT = 'Waiting for camera...'


class ZoneStoreProtocol(Protocol):
    """Structural interface the MJPEG generator depends on for zone reads."""

    def list_zones(self) -> tuple[list[Zone], int]:
        """Return (zones, version)."""
        ...  # pragma: no cover


@lru_cache(maxsize=1)
def _placeholder_jpeg() -> bytes:
    """Return a cached JPEG-encoded placeholder frame."""
    frame = np.full(_PLACEHOLDER_SIZE, 40, dtype=np.uint8)
    cv2.putText(
        frame,
        _PLACEHOLDER_TEXT,
        (20, 240),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.8,
        (200, 200, 200),
        2,
    )
    return _encode_jpeg(frame)


def _encode_jpeg(frame: np.ndarray) -> bytes:
    """JPEG-encode *frame*; raises ValueError if encoding fails."""
    ok, buf = cv2.imencode('.jpg', frame)
    if not ok:  # pragma: no cover
        raise ValueError('JPEG encoding failed for MJPEG stream frame')
    return buf.tobytes()


def _multipart_part(jpeg_bytes: bytes) -> bytes:
    """Wrap *jpeg_bytes* in one multipart/x-mixed-replace part."""
    return _BOUNDARY + b'\r\nContent-Type: image/jpeg\r\n\r\n' + jpeg_bytes + b'\r\n'


def generate_mjpeg_stream(
    state: DashboardState,
    settings: ClientSettings,
    zone_store: ZoneStoreProtocol,
    clock: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
    annotate_fn: Callable = annotate_frame,
    max_frames: int | None = None,
) -> Iterator[bytes]:
    """Yield rate-limited, annotated JPEG multipart parts.

    Serves a cached placeholder until a real frame is available. Bounds the
    emission rate to ``1 / settings.web_stream_fps`` using the injected
    *clock*/*sleep*. Stops after *max_frames* parts if given (production
    callers pass None and rely on the client disconnecting to stop the
    generator; tests pass a small bound).

    Zones are read via *zone_store*'s ``list_zones()`` rather than
    ``settings.zones`` directly, since the zone list is mutated concurrently
    from the Flask zone-CRUD thread; ``list_zones()`` returns a lock-guarded
    snapshot safe to read from this thread.
    """
    interval = 1.0 / settings.web_stream_fps
    emitted = 0
    while max_frames is None or emitted < max_frames:
        start = clock()
        frame = state.get_frame()
        if frame is None:
            jpeg = _placeholder_jpeg()
        else:
            detection = state.get_detection()
            zones, _ = zone_store.list_zones()
            enabled_zones = [zone for zone in zones if zone.enabled]
            annotated = annotate_fn(
                frame,
                detection.detections,
                enabled_zones,
                detection.triggered_zones,
                elevated=detection.elevated,
            )
            jpeg = _encode_jpeg(annotated)
        yield _multipart_part(jpeg)
        emitted += 1
        elapsed = clock() - start
        remaining = interval - elapsed
        if remaining > 0:
            sleep(remaining)
