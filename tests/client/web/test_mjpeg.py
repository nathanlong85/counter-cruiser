"""Tests for the MJPEG generator: rate limiting, placeholder, shared annotation."""

from __future__ import annotations

import numpy as np

from counter_cruiser.client.web.mjpeg import generate_mjpeg_stream
from counter_cruiser.client.web.state import DashboardState
from counter_cruiser.client.web.zone_store import ZoneStore
from counter_cruiser.config.models import ClientSettings, Zone
from counter_cruiser.shared.protocol import BoundingBox


class FakeZoneStore:
    """Zone-store double: returns a fixed zone list, no persistence."""

    def __init__(self, zones: list[Zone] | None = None) -> None:
        self._zones = zones or []

    def list_zones(self) -> tuple[list[Zone], int]:
        return list(self._zones), 0


class FakeClock:
    """Deterministic clock/sleep pair: each sleep() call advances the clock."""

    def __init__(self) -> None:
        self.now = 0.0
        self.sleep_calls: list[float] = []

    def time(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.sleep_calls.append(seconds)
        self.now += seconds


def test_no_frame_yet_serves_placeholder() -> None:
    state = DashboardState()
    settings = ClientSettings()
    clock = FakeClock()
    parts = list(
        generate_mjpeg_stream(
            state,
            settings,
            FakeZoneStore(),
            clock=clock.time,
            sleep=clock.sleep,
            max_frames=1,
        )
    )
    assert len(parts) == 1
    assert b'--frame' in parts[0]
    assert b'Content-Type: image/jpeg' in parts[0]


def test_serves_real_frame_once_available() -> None:
    state = DashboardState()
    settings = ClientSettings()
    clock = FakeClock()
    placeholder_parts = list(
        generate_mjpeg_stream(
            state,
            settings,
            FakeZoneStore(),
            clock=clock.time,
            sleep=clock.sleep,
            max_frames=1,
        )
    )
    state.update_frame(np.ones((10, 10, 3), dtype=np.uint8) * 200)
    real_parts = list(
        generate_mjpeg_stream(
            state,
            settings,
            FakeZoneStore(),
            clock=clock.time,
            sleep=clock.sleep,
            max_frames=1,
        )
    )
    assert placeholder_parts[0] != real_parts[0]


def test_emission_rate_is_bounded_by_configured_fps() -> None:
    state = DashboardState()
    state.update_frame(np.zeros((10, 10, 3), dtype=np.uint8))
    settings = ClientSettings(web_stream_fps=2.0)
    clock = FakeClock()
    list(
        generate_mjpeg_stream(
            state,
            settings,
            FakeZoneStore(),
            clock=clock.time,
            sleep=clock.sleep,
            max_frames=3,
        )
    )
    assert len(clock.sleep_calls) == 3
    for call in clock.sleep_calls:
        assert call == 0.5  # 1 / 2.0 fps, zero elapsed time under the fake clock


def test_no_sleep_when_processing_exceeds_the_frame_interval() -> None:
    """Covers the branch where elapsed time already meets/exceeds the interval.

    Not part of the task brief's transcribed test set — added to close a
    coverage gap (the `if remaining > 0` false branch) required by this
    project's 100% branch-coverage policy.
    """
    state = DashboardState()
    state.update_frame(np.zeros((10, 10, 3), dtype=np.uint8))
    settings = ClientSettings(web_stream_fps=2.0)  # interval = 0.5s
    times = iter([0.0, 1.0])  # elapsed (1.0 - 0.0) exceeds the 0.5s interval
    sleep_calls: list[float] = []

    list(
        generate_mjpeg_stream(
            state,
            settings,
            FakeZoneStore(),
            clock=lambda: next(times),
            sleep=sleep_calls.append,
            max_frames=1,
        )
    )

    assert sleep_calls == []


def test_annotation_invoked_with_current_frame_detections_zones_status() -> None:
    state = DashboardState()
    frame = np.zeros((10, 10, 3), dtype=np.uint8)
    state.update_frame(frame)
    box = BoundingBox(
        x1=1, y1=1, x2=2, y2=2, confidence=0.9, class_id=16, class_name='dog'
    )
    state.update_detection([box], {'z1'}, elevated=True)
    zone = Zone(id='z1', name='Counter', enabled=True, polygon=[(0, 0), (9, 0), (9, 9)])
    disabled_zone = Zone(
        id='z2', name='Off', enabled=False, polygon=[(0, 0), (9, 0), (9, 9)]
    )
    settings = ClientSettings(zones=[zone, disabled_zone])
    zone_store = FakeZoneStore([zone, disabled_zone])
    clock = FakeClock()

    calls = []

    def spy_annotate(frame_arg, detections, zones, triggered_zones, elevated):
        calls.append((frame_arg, detections, zones, triggered_zones, elevated))
        return frame_arg

    list(
        generate_mjpeg_stream(
            state,
            settings,
            zone_store,
            clock=clock.time,
            sleep=clock.sleep,
            annotate_fn=spy_annotate,
            max_frames=1,
        )
    )
    assert len(calls) == 1
    called_frame, detections, zones, triggered_zones, elevated = calls[0]
    np.testing.assert_array_equal(called_frame, frame)
    assert detections == [box]
    assert zones == [zone]  # only the enabled zone is passed
    assert triggered_zones == {'z1'}
    assert elevated is True


def test_zones_are_read_through_zone_store_not_raw_settings() -> None:
    """Regression test for the settings.zones/zone_store data race fix.

    The generator must read zones via ``zone_store.list_zones()`` — a
    lock-guarded snapshot — rather than ``settings.zones`` directly, since
    the zone list is mutated concurrently from the Flask zone-CRUD thread.
    """
    state = DashboardState()
    state.update_frame(np.zeros((10, 10, 3), dtype=np.uint8))
    stale_zone = Zone(
        id='stale', name='Stale', enabled=True, polygon=[(0, 0), (9, 0), (9, 9)]
    )
    fresh_zone = Zone(
        id='fresh', name='Fresh', enabled=True, polygon=[(0, 0), (9, 0), (9, 9)]
    )
    # settings.zones deliberately differs from the zone store's zones: if the
    # generator reads settings.zones directly, this assertion catches it.
    settings = ClientSettings(zones=[stale_zone])
    zone_store = FakeZoneStore([fresh_zone])
    clock = FakeClock()

    calls = []

    def spy_annotate(frame_arg, detections, zones, triggered_zones, elevated):
        calls.append(zones)
        return frame_arg

    list(
        generate_mjpeg_stream(
            state,
            settings,
            zone_store,
            clock=clock.time,
            sleep=clock.sleep,
            annotate_fn=spy_annotate,
            max_frames=1,
        )
    )
    assert calls == [[fresh_zone]]


def test_zone_store_is_used_via_the_zonestore_class(tmp_path) -> None:
    """Confirm the real ZoneStore (not just a fake) satisfies the generator."""
    zone = Zone(id='z1', name='Counter', enabled=True, polygon=[(0, 0), (9, 0), (9, 9)])
    config_path = tmp_path / 'client.toml'
    config_path.write_text('')
    settings = ClientSettings(zones=[zone])
    zone_store = ZoneStore(settings, config_path)
    state = DashboardState()
    state.update_frame(np.zeros((10, 10, 3), dtype=np.uint8))
    clock = FakeClock()

    parts = list(
        generate_mjpeg_stream(
            state,
            settings,
            zone_store,
            clock=clock.time,
            sleep=clock.sleep,
            max_frames=1,
        )
    )
    assert len(parts) == 1
