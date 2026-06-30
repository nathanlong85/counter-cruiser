"""Tests for shared geometry helpers."""
from counter_cruiser.config.models import Zone
from counter_cruiser.shared.geometry import (
    FrameAnalysis,
    analyze_detections,
    analyze_dog_position,
    check_zones,
)
from counter_cruiser.shared.protocol import BoundingBox


def _zone(
    id: str = 'z1',
    polygon: list[tuple[int, int]] | None = None,
    enabled: bool = True,
) -> Zone:
    if polygon is None:
        polygon = [(100, 100), (300, 100), (300, 300), (100, 300)]
    return Zone(id=id, name=id, enabled=enabled, polygon=polygon)


def _box(x1: int = 150, y1: int = 150, x2: int = 250, y2: int = 250) -> BoundingBox:
    return BoundingBox(x1=x1, y1=y1, x2=x2, y2=y2, confidence=0.9, class_id=16, class_name='dog')


class TestCheckZones:
    def test_point_inside_zone_triggers_it(self) -> None:
        box = _box(150, 150, 250, 250)  # center (200,200) inside z1 square
        result = check_zones(box, [_zone('z1')])
        assert result == ['z1']

    def test_box_outside_all_zones_triggers_nothing(self) -> None:
        box = _box(400, 400, 500, 500)  # entirely outside z1 (100-300,100-300)
        result = check_zones(box, [_zone('z1')])
        assert result == []

    def test_disabled_zone_is_ignored(self) -> None:
        box = _box(150, 150, 250, 250)
        result = check_zones(box, [_zone('z1', enabled=False)])
        assert result == []

    def test_box_can_trigger_multiple_zones(self) -> None:
        z1 = _zone('z1', polygon=[(0, 0), (300, 0), (300, 300), (0, 300)])
        z2 = _zone('z2', polygon=[(100, 100), (400, 100), (400, 400), (100, 400)])
        box = _box(150, 150, 250, 250)  # center (200,200) inside both
        result = check_zones(box, [z1, z2])
        assert sorted(result) == ['z1', 'z2']

    def test_no_zones_returns_empty(self) -> None:
        assert check_zones(_box(), []) == []


class TestAnalyzeDogPosition:
    """size_ratio = box_height / frame_height; elevated = ratio > min AND in zone."""

    def test_large_dog_in_zone_is_elevated(self) -> None:
        box = _box(100, 0, 200, 300)  # height=300, frame=480 → ratio=0.625 > 0.25; inside z1
        z = _zone('z1', polygon=[(0, 0), (640, 0), (640, 480), (0, 480)])
        elevated, zones = analyze_dog_position(box, [z], frame_height=480, min_size_ratio=0.25)
        assert elevated is True
        assert zones == ['z1']

    def test_large_dog_outside_zone_not_elevated(self) -> None:
        box = _box(350, 0, 450, 300)  # height=300 > 0.25×480; but entirely outside z1 (100-300,100-300)
        elevated, zones = analyze_dog_position(
            box, [_zone('z1')], frame_height=480, min_size_ratio=0.25
        )
        assert elevated is False
        assert zones == []

    def test_small_dog_in_zone_not_elevated(self) -> None:
        box = _box(150, 150, 250, 200)  # height=50; ratio≈0.10 < 0.25; inside z1
        elevated, zones = analyze_dog_position(
            box, [_zone('z1')], frame_height=480, min_size_ratio=0.25
        )
        assert elevated is False
        assert zones == ['z1']

    def test_size_ratio_computed_from_frame_height(self) -> None:
        """Box height == min threshold exactly → not elevated (strictly greater)."""
        # box height = 120, frame_height = 480, ratio = 0.25 == min_size_ratio → NOT elevated
        box = _box(150, 100, 250, 220)  # height=120
        z = _zone('z1', polygon=[(0, 0), (640, 0), (640, 480), (0, 480)])
        elevated, _ = analyze_dog_position(box, [z], frame_height=480, min_size_ratio=0.25)
        assert elevated is False


class TestAnalyzeDetections:
    _full_zone = Zone(
        id='z1', name='Zone 1', enabled=True,
        polygon=[(0, 0), (640, 0), (640, 480), (0, 480)],
    )

    def _big_box(self) -> BoundingBox:
        """Box with height=300 → ratio=0.625 > 0.25; inside full zone."""
        return BoundingBox(x1=0, y1=0, x2=100, y2=300, confidence=0.9, class_id=16, class_name='dog')

    def _small_box(self) -> BoundingBox:
        """Box with height=50 → ratio≈0.10 < 0.25."""
        return BoundingBox(x1=0, y1=0, x2=100, y2=50, confidence=0.9, class_id=16, class_name='dog')

    def test_any_elevated_marks_frame_elevated(self) -> None:
        result = analyze_detections(
            [self._small_box(), self._big_box()], [self._full_zone], 480, 0.25
        )
        assert result.elevated is True

    def test_triggered_zones_unioned_across_elevated(self) -> None:
        z2 = Zone(id='z2', name='Zone 2', enabled=True, polygon=[(0, 0), (640, 0), (640, 480), (0, 480)])
        result = analyze_detections(
            [self._big_box(), self._big_box()], [self._full_zone, z2], 480, 0.25
        )
        assert result.triggered_zones == {'z1', 'z2'}

    def test_no_detections_returns_not_elevated(self) -> None:
        result = analyze_detections([], [self._full_zone], 480, 0.25)
        assert result.elevated is False
        assert result.triggered_zones == set()

    def test_result_is_frame_analysis(self) -> None:
        result = analyze_detections([], [], 480, 0.25)
        assert isinstance(result, FrameAnalysis)
