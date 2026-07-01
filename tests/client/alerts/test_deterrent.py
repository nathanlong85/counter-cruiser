"""Tests for DeterrentHandler: GPIO button-press simulation."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from counter_cruiser.client.alerts.context import AlertContext
from counter_cruiser.client.alerts.deterrent import DeterrentHandler, _import_gpio
from counter_cruiser.config.models import DeterrentConfig


def _context() -> AlertContext:
    return AlertContext(
        frame=None, detections=[], zones=[], triggered_zones={'z1'}, frame_id=1
    )


def _fake_gpio() -> MagicMock:
    gpio = MagicMock()
    gpio.BCM = 'BCM'
    gpio.OUT = 'OUT'
    gpio.HIGH = 1
    gpio.LOW = 0
    return gpio


class TestDeterrentBurst:
    def test_burst_drives_pin_high_then_low(self) -> None:
        gpio = _fake_gpio()
        config = DeterrentConfig(enabled=True, pin=17, burst_duration_seconds=0.01)
        with (
            patch(
                'counter_cruiser.client.alerts.deterrent._import_gpio',
                return_value=gpio,
            ),
            patch('counter_cruiser.client.alerts.deterrent.time.sleep'),
        ):
            handler = DeterrentHandler(config)
            handler.trigger(_context())

        gpio.setup.assert_called_once_with(17, gpio.OUT, initial=gpio.LOW)
        assert gpio.output.call_args_list == [
            ((17, gpio.HIGH),),
            ((17, gpio.LOW),),
        ]

    def test_burst_uses_configured_duration(self) -> None:
        gpio = _fake_gpio()
        config = DeterrentConfig(enabled=True, pin=17, burst_duration_seconds=2.5)
        with (
            patch(
                'counter_cruiser.client.alerts.deterrent._import_gpio',
                return_value=gpio,
            ),
            patch('counter_cruiser.client.alerts.deterrent.time.sleep') as sleep,
        ):
            handler = DeterrentHandler(config)
            handler.trigger(_context())

        sleep.assert_called_once_with(2.5)


class TestDeterrentMustNotFireContinuously:
    def test_pin_driven_low_after_a_normal_burst(self) -> None:
        gpio = _fake_gpio()
        config = DeterrentConfig(enabled=True, pin=17, burst_duration_seconds=0.01)
        with (
            patch(
                'counter_cruiser.client.alerts.deterrent._import_gpio',
                return_value=gpio,
            ),
            patch('counter_cruiser.client.alerts.deterrent.time.sleep'),
        ):
            handler = DeterrentHandler(config)
            handler.trigger(_context())

        assert gpio.output.call_args_list[-1] == ((17, gpio.LOW),)

    def test_pin_driven_low_and_error_logged_when_burst_raises(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        gpio = _fake_gpio()
        config = DeterrentConfig(enabled=True, pin=17, burst_duration_seconds=0.01)
        with (
            patch(
                'counter_cruiser.client.alerts.deterrent._import_gpio',
                return_value=gpio,
            ),
            patch(
                'counter_cruiser.client.alerts.deterrent.time.sleep',
                side_effect=RuntimeError('boom'),
            ),
            caplog.at_level('ERROR'),
        ):
            handler = DeterrentHandler(config)
            handler.trigger(_context())

        assert gpio.output.call_args_list[-1] == ((17, gpio.LOW),)
        assert 'Deterrent burst failed' in caplog.text


class TestDeterrentGracefulDegradation:
    def test_missing_gpio_library_disables_handler_with_log(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        config = DeterrentConfig(enabled=True, pin=17)
        with (
            patch(
                'counter_cruiser.client.alerts.deterrent._import_gpio',
                return_value=None,
            ),
            caplog.at_level('WARNING'),
        ):
            handler = DeterrentHandler(config)
        assert 'RPi.GPIO unavailable' in caplog.text
        # Trigger after disablement is a silent no-op.
        handler.trigger(_context())

    def test_gpio_setup_failure_disables_handler_with_log(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        gpio = _fake_gpio()
        gpio.setup.side_effect = RuntimeError('no such pin')
        config = DeterrentConfig(enabled=True, pin=17)
        with (
            patch(
                'counter_cruiser.client.alerts.deterrent._import_gpio',
                return_value=gpio,
            ),
            caplog.at_level('ERROR'),
        ):
            handler = DeterrentHandler(config)
        assert 'GPIO setup failed' in caplog.text
        handler.trigger(_context())
        gpio.output.assert_not_called()

    def test_disabled_by_config_trigger_is_a_noop(self) -> None:
        config = DeterrentConfig(enabled=False)
        with patch(
            'counter_cruiser.client.alerts.deterrent._import_gpio'
        ) as import_gpio:
            handler = DeterrentHandler(config)
            handler.trigger(_context())
        import_gpio.assert_not_called()


class TestImportGpio:
    def test_import_gpio_returns_none_when_unavailable(self) -> None:
        # Direct call to real _import_gpio (RPi.GPIO not installed in test env)
        result = _import_gpio()
        assert result is None


class TestDeterrentCleanup:
    def test_cleanup_releases_gpio_after_init(self) -> None:
        gpio = _fake_gpio()
        config = DeterrentConfig(enabled=True, pin=17)
        with patch(
            'counter_cruiser.client.alerts.deterrent._import_gpio',
            return_value=gpio,
        ):
            handler = DeterrentHandler(config)
            handler.cleanup()
        gpio.cleanup.assert_called_once_with()

    def test_cleanup_is_safe_when_disabled(self) -> None:
        config = DeterrentConfig(enabled=False)
        handler = DeterrentHandler(config)
        handler.cleanup()  # must not raise
