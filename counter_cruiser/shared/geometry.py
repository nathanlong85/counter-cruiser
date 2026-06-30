"""Pure geometry helpers for zone containment and elevated-dog classification."""
from __future__ import annotations

import cv2
import numpy as np

from counter_cruiser.config.models import Zone
from counter_cruiser.shared.protocol import BoundingBox


def box_test_points(box: BoundingBox) -> list[tuple[float, float]]:
    """Return the four corners and centre of a bounding box."""
    cx = (box.x1 + box.x2) / 2.0
    cy = (box.y1 + box.y2) / 2.0
    return [
        (float(box.x1), float(box.y1)),
        (float(box.x2), float(box.y1)),
        (float(box.x2), float(box.y2)),
        (float(box.x1), float(box.y2)),
        (cx, cy),
    ]


def check_zones(box: BoundingBox, zones: list[Zone]) -> list[str]:
    """Return zone ids whose polygon contains any test point of *box*.

    Disabled zones are always skipped.
    """
    triggered: list[str] = []
    for zone in zones:
        if not zone.enabled:
            continue
        polygon = np.array(zone.polygon, dtype=np.float32)
        for pt in box_test_points(box):
            if cv2.pointPolygonTest(polygon, pt, False) >= 0:
                triggered.append(zone.id)
                break
    return triggered
