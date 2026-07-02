"""Integration test: debounced elevated event reaches AlertManager."""

from __future__ import annotations

from unittest.mock import MagicMock

from counter_cruiser.client.alerts.context import AlertContext
from counter_cruiser.client.alerts.manager import AlertManager
from counter_cruiser.config.models import Zone
from counter_cruiser.shared.debounce import DetectionHistory
from counter_cruiser.shared.geometry import analyze_detections
from counter_cruiser.shared.protocol import BoundingBox, DetectionMessage


def _elevated_box() -> BoundingBox:
    return BoundingBox(
        x1=0, y1=0, x2=200, y2=400, confidence=0.9, class_id=16, class_name='dog'
    )


class TestDebounceToAlertManagerWiring:
    def test_debounced_elevated_event_invokes_alert_manager(self) -> None:
        zone = Zone(
            id='counter', name='Counter', polygon=[(0, 0), (640, 0), (640, 480)]
        )
        history = DetectionHistory()
        alert_manager = MagicMock(spec=AlertManager)
        frame_height = 480
        min_size_ratio = 0.25
        zones = [zone]

        def on_result(msg: DetectionMessage) -> None:
            analysis = analyze_detections(
                msg.boxes, zones, frame_height, min_size_ratio
            )
            history.add(msg.frame_id, analysis.elevated)
            if history.is_consecutive_elevated():
                context = AlertContext(
                    frame=None,
                    detections=msg.boxes,
                    zones=zones,
                    triggered_zones=analysis.triggered_zones,
                    frame_id=msg.frame_id,
                )
                alert_manager.maybe_alert(context)

        # First elevated frame: debounce not yet satisfied.
        on_result(
            DetectionMessage(
                frame_id=1, boxes=[_elevated_box()], processing_time_ms=1.0
            )
        )
        alert_manager.maybe_alert.assert_not_called()

        # Second consecutive elevated frame: debounce satisfied, dispatch fires.
        on_result(
            DetectionMessage(
                frame_id=2, boxes=[_elevated_box()], processing_time_ms=1.0
            )
        )
        alert_manager.maybe_alert.assert_called_once()
        context = alert_manager.maybe_alert.call_args[0][0]
        assert context.triggered_zones == {'counter'}
        assert context.frame_id == 2
