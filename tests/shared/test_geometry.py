"""Tests for shared geometry helpers."""
import numpy as np
import pytest

from counter_cruiser.config.models import Zone
from counter_cruiser.shared.geometry import check_zones
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
