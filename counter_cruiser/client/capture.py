"""Camera capture interface and OpenCV implementation."""

from __future__ import annotations

import logging
from typing import Protocol

import cv2
import numpy as np

logger = logging.getLogger(__name__)


class CameraCapture(Protocol):
    """Protocol for camera frame sources; injectable for testing."""

    def open(self, index: int, width: int, height: int) -> tuple[int, int]:
        """Open the camera and configure resolution; return actual (width, height)."""
        ...  # pragma: no cover

    def read(self) -> np.ndarray | None:
        """Read and return the next frame, or None on transient failure."""
        ...  # pragma: no cover

    def release(self) -> None:
        """Release the camera resource."""
        ...  # pragma: no cover


class OpenCVCapture:
    """Real camera implementation backed by ``cv2.VideoCapture``."""

    def __init__(self) -> None:
        """Create an unopened capture instance."""
        self._cap: cv2.VideoCapture | None = None

    def open(self, index: int, width: int, height: int) -> tuple[int, int]:
        """Open camera at *index*, set requested resolution, return actual (w, h).

        Raises ``RuntimeError`` if the camera cannot be opened.
        """
        cap = cv2.VideoCapture(index)
        if not cap.isOpened():
            raise RuntimeError(f'Cannot open camera at index {index}')
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
        self._cap = cap
        actual_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        actual_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        logger.info('Camera %d opened at %dx%d', index, actual_w, actual_h)
        return actual_w, actual_h

    def read(self) -> np.ndarray | None:
        """Return the next BGR frame, or None if the read failed."""
        if self._cap is None:
            return None
        ok, frame = self._cap.read()
        return frame if ok else None

    def release(self) -> None:
        """Release the underlying VideoCapture."""
        if self._cap is not None:
            self._cap.release()
            self._cap = None
