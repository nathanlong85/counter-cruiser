"""Pure geometry helpers for zone containment and elevated-dog classification."""

from __future__ import annotations

from dataclasses import dataclass, field

import cv2
import numpy as np

from counter_cruiser.config.models import Zone
from counter_cruiser.shared.protocol import BoundingBox


@dataclass
class FrameAnalysis:
    """Aggregate analysis result for a single video frame."""

    elevated: bool
    triggered_zones: set[str] = field(default_factory=set)


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


def analyze_dog_position(
    box: BoundingBox,
    zones: list[Zone],
    frame_height: int,
    min_size_ratio: float,
) -> tuple[bool, list[str]]:
    """Classify a single detection as elevated or floor.

    Returns (is_elevated, list_of_triggered_zone_ids).
    Elevated requires size_ratio > min_size_ratio AND at least one zone triggered.
    """
    size_ratio = (box.y2 - box.y1) / frame_height
    triggered = check_zones(box, zones)
    is_elevated = size_ratio > min_size_ratio and len(triggered) > 0
    return is_elevated, triggered


def analyze_detections(
    boxes: list[BoundingBox],
    zones: list[Zone],
    frame_height: int,
    min_size_ratio: float,
) -> FrameAnalysis:
    """Aggregate per-box results into a single frame-level analysis."""
    all_zones: set[str] = set()
    elevated = False
    for box in boxes:
        is_el, zone_ids = analyze_dog_position(box, zones, frame_height, min_size_ratio)
        if is_el:
            elevated = True
            all_zones.update(zone_ids)
    return FrameAnalysis(elevated=elevated, triggered_zones=all_zones)
