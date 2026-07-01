"""Tests for AlertManager: cooldown, deterrent-first fan-out, isolation."""

from __future__ import annotations

from counter_cruiser.client.alerts.context import AlertContext
from counter_cruiser.client.alerts.manager import AlertManager


class FakeHandler:
    """Records calls; can be configured to raise on trigger/cleanup."""

    def __init__(
        self, name: str, raise_on_trigger: bool = False, raise_on_cleanup: bool = False
    ):
        self.name = name
        self.trigger_calls: list[AlertContext] = []
        self.cleanup_calls = 0
        self._raise_on_trigger = raise_on_trigger
        self._raise_on_cleanup = raise_on_cleanup

    def trigger(self, context: AlertContext) -> None:
        self.trigger_calls.append(context)
        if self._raise_on_trigger:
            raise RuntimeError(f'{self.name} trigger failed')

    def cleanup(self) -> None:
        self.cleanup_calls += 1
        if self._raise_on_cleanup:
            raise RuntimeError(f'{self.name} cleanup failed')


def _context(zones: set[str], frame_id: int = 1) -> AlertContext:
    return AlertContext(
        frame=None, detections=[], zones=[], triggered_zones=zones, frame_id=frame_id
    )


class TestCooldown:
    def test_proceeds_when_zone_outside_window(self) -> None:
        handler = FakeHandler('h1')
        manager = AlertManager(handlers=[handler], cooldown_seconds=100.0)
        manager.maybe_alert(_context({'z1'}))
        assert len(handler.trigger_calls) == 1

    def test_suppresses_when_all_zones_within_window(self) -> None:
        handler = FakeHandler('h1')
        manager = AlertManager(handlers=[handler], cooldown_seconds=100.0)
        manager.maybe_alert(_context({'z1'}))
        manager.maybe_alert(_context({'z1'}))
        assert len(handler.trigger_calls) == 1

    def test_proceeds_and_records_last_alert_for_all_triggered_zones(self) -> None:
        handler = FakeHandler('h1')
        manager = AlertManager(handlers=[handler], cooldown_seconds=100.0)
        manager.maybe_alert(_context({'z1', 'z2'}))
        # Second alert only for z2 should be suppressed too, since z2's
        # last-alert time was recorded on the first (multi-zone) call.
        manager.maybe_alert(_context({'z2'}))
        assert len(handler.trigger_calls) == 1

    def test_zones_tracked_independently(self) -> None:
        handler = FakeHandler('h1')
        manager = AlertManager(handlers=[handler], cooldown_seconds=100.0)
        manager.maybe_alert(_context({'z1'}))
        manager.maybe_alert(_context({'z2'}))  # different zone, not suppressed
        assert len(handler.trigger_calls) == 2

    def test_zero_cooldown_never_suppresses(self) -> None:
        handler = FakeHandler('h1')
        manager = AlertManager(handlers=[handler], cooldown_seconds=0.0)
        manager.maybe_alert(_context({'z1'}))
        manager.maybe_alert(_context({'z1'}))
        assert len(handler.trigger_calls) == 2

    def test_empty_triggered_zones_never_suppressed(self) -> None:
        handler = FakeHandler('h1')
        manager = AlertManager(handlers=[handler], cooldown_seconds=100.0)
        manager.maybe_alert(_context(set()))
        manager.maybe_alert(_context(set()))
        assert len(handler.trigger_calls) == 2


class TestFanOut:
    def test_all_handlers_run_once(self) -> None:
        h1, h2 = FakeHandler('h1'), FakeHandler('h2')
        manager = AlertManager(handlers=[h1, h2], cooldown_seconds=0.0)
        manager.maybe_alert(_context({'z1'}))
        assert len(h1.trigger_calls) == 1
        assert len(h2.trigger_calls) == 1

    def test_deterrent_fires_before_any_other_handler(self) -> None:
        order: list[str] = []

        class OrderTrackingHandler(FakeHandler):
            def trigger(self, context: AlertContext) -> None:
                order.append(self.name)
                super().trigger(context)

        deterrent = OrderTrackingHandler('deterrent')
        snapshot = OrderTrackingHandler('snapshot')
        log = OrderTrackingHandler('log')
        manager = AlertManager(
            handlers=[snapshot, log], cooldown_seconds=0.0, deterrent=deterrent
        )
        manager.maybe_alert(_context({'z1'}))
        assert order == ['deterrent', 'snapshot', 'log']

    def test_no_deterrent_configured_runs_remaining_handlers(self) -> None:
        handler = FakeHandler('h1')
        manager = AlertManager(handlers=[handler], cooldown_seconds=0.0, deterrent=None)
        manager.maybe_alert(_context({'z1'}))
        assert len(handler.trigger_calls) == 1


class TestFailureIsolation:
    def test_one_handler_raising_still_runs_the_others(self, caplog) -> None:
        failing = FakeHandler('failing', raise_on_trigger=True)
        ok = FakeHandler('ok')
        manager = AlertManager(handlers=[failing, ok], cooldown_seconds=0.0)
        with caplog.at_level('ERROR'):
            manager.maybe_alert(_context({'z1'}))  # must not raise
        assert len(ok.trigger_calls) == 1
        assert 'FakeHandler' in caplog.text


class TestCleanup:
    def test_all_handlers_cleaned_up(self) -> None:
        deterrent = FakeHandler('deterrent')
        h1, h2 = FakeHandler('h1'), FakeHandler('h2')
        manager = AlertManager(
            handlers=[h1, h2], cooldown_seconds=0.0, deterrent=deterrent
        )
        manager.cleanup()
        assert deterrent.cleanup_calls == 1
        assert h1.cleanup_calls == 1
        assert h2.cleanup_calls == 1

    def test_one_failing_cleanup_does_not_block_the_rest(self, caplog) -> None:
        failing = FakeHandler('failing', raise_on_cleanup=True)
        ok = FakeHandler('ok')
        manager = AlertManager(handlers=[failing, ok], cooldown_seconds=0.0)
        with caplog.at_level('ERROR'):
            manager.cleanup()  # must not raise
        assert ok.cleanup_calls == 1
