"""Detection model abstraction and device selection for the inference server."""

from __future__ import annotations

from abc import ABC, abstractmethod

import numpy as np

from counter_cruiser.shared.protocol import BoundingBox

DOG_CLASS_ID = 16  # COCO dataset index for "dog"

# Imported at module level so tests can patch it without importing torch/ultralytics
try:
    # Whether this succeeds or raises depends on whether the optional
    # 'server' extra (torch/ultralytics) is installed; in any single dev/CI
    # environment only one of the try/except branches is exercisable, so
    # both sides are marked no cover.
    import torch  # pragma: no cover
    from ultralytics import YOLO  # pragma: no cover
except ImportError:  # pragma: no cover
    torch = None  # type: ignore[assignment]
    YOLO = None  # type: ignore[assignment]


class DetectionModel(ABC):
    """Abstract base for pluggable detection models."""

    @abstractmethod
    def detect(self, frame: np.ndarray) -> list[BoundingBox]:
        """Run inference on *frame*; return dog detections above threshold."""


class YOLOAdapter(DetectionModel):
    """Wraps an ``ultralytics.YOLO`` model, filtering to dogs above threshold."""

    def __init__(
        self, model_name: str, device: str, confidence_threshold: float
    ) -> None:
        """Load the YOLO model once at construction time."""
        self._model = YOLO(model_name)
        self._device = device
        self._threshold = confidence_threshold

    def detect(self, frame: np.ndarray) -> list[BoundingBox]:
        """Return dog :class:`BoundingBox` objects for detections above threshold."""
        results = self._model(frame, device=self._device, verbose=False)
        boxes: list[BoundingBox] = []
        for result in results:
            for box in result.boxes:
                cls_id = int(box.cls[0])
                conf = float(box.conf[0])
                if cls_id != DOG_CLASS_ID or conf < self._threshold:
                    continue
                x1, y1, x2, y2 = (int(v) for v in box.xyxy[0])
                boxes.append(
                    BoundingBox(
                        x1=x1,
                        y1=y1,
                        x2=x2,
                        y2=y2,
                        confidence=conf,
                        class_id=cls_id,
                        class_name='dog',
                    ),
                )
        return boxes


def select_device(device: str) -> str:
    """Resolve the compute device string.

    ``'auto'`` selects CUDA if available, then MPS, then CPU.
    Any other value is returned unchanged.
    """
    if device != 'auto':
        return device
    if torch is not None:
        if torch.cuda.is_available():
            return 'cuda:0'
        if hasattr(torch.backends, 'mps') and torch.backends.mps.is_available():
            return 'mps'
    return 'cpu'
