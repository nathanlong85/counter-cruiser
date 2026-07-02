"""Tests for the reusable frame-annotation helper."""

from __future__ import annotations

import numpy as np

from counter_cruiser.client.annotation import annotate_frame
from counter_cruiser.config.models import Zone
from counter_cruiser.shared.protocol import BoundingBox


def _frame() -> np.ndarray:
    return np.zeros((100, 100, 3), dtype=np.uint8)


def _box() -> BoundingBox:
    return BoundingBox(
        x1=10, y1=10, x2=50, y2=50, confidence=0.9, class_id=16, class_name='dog'
    )


def _zone(zone_id: str = 'z1') -> Zone:
    return Zone(id=zone_id, name='Counter', polygon=[(0, 0), (99, 0), (99, 99)])


class TestAnnotateFrame:
    def test_boxes_drawn_when_enabled(self) -> None:
        annotated = annotate_frame(
            _frame(), [_box()], [], set(), include_boxes=True, include_zones=False
        )
        assert not np.array_equal(annotated, _frame())

    def test_zones_drawn_when_enabled(self) -> None:
        annotated = annotate_frame(
            _frame(), [], [_zone()], set(), include_boxes=False, include_zones=True
        )
        assert not np.array_equal(annotated, _frame())

    def test_no_overlay_when_both_disabled(self) -> None:
        annotated = annotate_frame(
            _frame(),
            [_box()],
            [_zone()],
            {'z1'},
            include_boxes=False,
            include_zones=False,
        )
        # Timestamp text is always drawn, so only compare the shape/dtype
        # and confirm no box/zone-colored pixels are present. Compare full
        # (B, G, R) triplets rather than broadcasting per-channel, since a
        # per-channel comparison trivially matches the all-zero background.
        assert annotated.shape == _frame().shape
        region = annotated[10:50, 10:50]
        red_pixel_mask = np.all(region == [0, 0, 255], axis=-1)
        assert not np.any(red_pixel_mask)

    def test_triggered_zone_drawn_distinctly_from_idle_zone(self) -> None:
        triggered = annotate_frame(
            _frame(), [], [_zone('z1')], {'z1'}, include_boxes=False, include_zones=True
        )
        idle = annotate_frame(
            _frame(), [], [_zone('z1')], set(), include_boxes=False, include_zones=True
        )
        assert not np.array_equal(triggered, idle)

    def test_original_frame_is_not_mutated(self) -> None:
        frame = _frame()
        original = frame.copy()
        annotate_frame(frame, [_box()], [_zone()], {'z1'})
        np.testing.assert_array_equal(frame, original)
