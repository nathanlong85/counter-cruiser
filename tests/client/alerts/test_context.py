"""Tests for AlertContext and the AlertHandler protocol."""

from __future__ import annotations

import numpy as np

from counter_cruiser.client.alerts.context import AlertContext, AlertHandler
from counter_cruiser.config.models import Zone
from counter_cruiser.shared.protocol import BoundingBox


def _box() -> BoundingBox:
    return BoundingBox(
        x1=0, y1=0, x2=10, y2=10, confidence=0.9, class_id=16, class_name='dog'
    )


class TestAlertContext:
    def test_construction_holds_all_fields(self) -> None:
        frame = np.zeros((10, 10, 3), dtype=np.uint8)
        zone = Zone(id='z1', name='Counter', polygon=[(0, 0), (10, 0), (10, 10)])
        ctx = AlertContext(
            frame=frame,
            detections=[_box()],
            zones=[zone],
            triggered_zones={'z1'},
            frame_id=42,
        )
        assert ctx.frame is frame
        assert ctx.detections == [_box()]
        assert ctx.zones == [zone]
        assert ctx.triggered_zones == {'z1'}
        assert ctx.frame_id == 42

    def test_frame_may_be_none(self) -> None:
        ctx = AlertContext(
            frame=None, detections=[], zones=[], triggered_zones=set(), frame_id=1
        )
        assert ctx.frame is None


class TestAlertHandlerProtocol:
    def test_a_conforming_object_satisfies_the_protocol(self) -> None:
        class FakeHandler:
            def trigger(self, context: AlertContext) -> None:
                return None

            def cleanup(self) -> None:
                return None

        handler: AlertHandler = FakeHandler()
        handler.trigger(
            AlertContext(
                frame=None, detections=[], zones=[], triggered_zones=set(), frame_id=1
            )
        )
        handler.cleanup()
