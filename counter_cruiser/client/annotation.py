"""Shared frame-annotation helper: boxes, zone polygons, and a timestamp.

Owned by the alert-system change and consumed (not reimplemented) by the
web-UI change's live-feed overlay. Pure function over plain data — no
globals, no I/O.
"""

from __future__ import annotations

from datetime import UTC, datetime

import cv2
import numpy as np

from counter_cruiser.config.models import Zone
from counter_cruiser.shared.protocol import BoundingBox

_ELEVATED_BOX_COLOR = (0, 0, 255)  # BGR red
_FLOOR_BOX_COLOR = (0, 200, 0)  # BGR green
_TRIGGERED_ZONE_COLOR = (0, 0, 255)  # BGR red
_IDLE_ZONE_COLOR = (0, 200, 0)  # BGR green
_TEXT_COLOR = (255, 255, 255)  # BGR white


def annotate_frame(
    frame: np.ndarray,
    detections: list[BoundingBox],
    zones: list[Zone],
    triggered_zones: set[str],
    include_boxes: bool = True,
    include_zones: bool = True,
    elevated: bool = True,
) -> np.ndarray:
    """Return a copy of *frame* overlaid with boxes, zones, and a timestamp.

    Detection boxes are drawn red when *elevated* is True, green otherwise.
    Triggered zones are drawn in red, idle zones in green. The timestamp is
    always drawn. *frame* itself is never mutated.
    """
    annotated = frame.copy()
    if include_boxes:
        box_color = _ELEVATED_BOX_COLOR if elevated else _FLOOR_BOX_COLOR
        for box in detections:
            cv2.rectangle(annotated, (box.x1, box.y1), (box.x2, box.y2), box_color, 2)
            label = f'{box.class_name} {box.confidence:.2f}'
            cv2.putText(
                annotated,
                label,
                (box.x1, max(box.y1 - 5, 0)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.5,
                box_color,
                1,
            )
    if include_zones:
        for zone in zones:
            pts = np.array(zone.polygon, dtype=np.int32).reshape((-1, 1, 2))
            color = (
                _TRIGGERED_ZONE_COLOR
                if zone.id in triggered_zones
                else _IDLE_ZONE_COLOR
            )
            cv2.polylines(annotated, [pts], isClosed=True, color=color, thickness=2)
    timestamp = datetime.now(UTC).strftime('%Y-%m-%d %H:%M:%S UTC')
    cv2.putText(
        annotated, timestamp, (10, 20), cv2.FONT_HERSHEY_SIMPLEX, 0.5, _TEXT_COLOR, 1
    )
    return annotated
