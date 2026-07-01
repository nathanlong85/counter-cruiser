"""Typed context passed to alert handlers, and the handler protocol."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import numpy as np

from counter_cruiser.config.models import Zone
from counter_cruiser.shared.protocol import BoundingBox


@dataclass
class AlertContext:
    """Everything a handler needs to record or react to one alert event."""

    frame: np.ndarray | None
    detections: list[BoundingBox]
    zones: list[Zone]
    triggered_zones: set[str]
    frame_id: int


class AlertHandler(Protocol):
    """Protocol for alert handlers; injectable and independently testable."""

    def trigger(self, context: AlertContext) -> None:
        """React to one dispatched alert. Must not raise."""
        ...  # pragma: no cover

    def cleanup(self) -> None:
        """Release any held resources. Must not raise."""
        ...  # pragma: no cover
