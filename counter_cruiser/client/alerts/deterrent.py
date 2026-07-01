"""GPIO deterrent handler: simulates a button press on the ultrasonic trainer.

The Pi does not generate the ultrasonic tone itself; it drives a BCM pin
HIGH for a configured duration (simulating the trainer's momentary-press
button) then LOW, wrapped in try/finally so the pin never stays HIGH.
"""

from __future__ import annotations

import logging
import time
from types import ModuleType

from counter_cruiser.client.alerts.context import AlertContext
from counter_cruiser.config.models import DeterrentConfig

logger = logging.getLogger(__name__)


def _import_gpio() -> ModuleType | None:
    """Import RPi.GPIO; return None if the library is unavailable.

    Isolated as a module-level function (not imported at module scope) so
    tests can patch this exact seam without needing the real library
    installed.
    """
    try:
        import RPi.GPIO as GPIO  # noqa: N814  # pragma: no cover
    except ImportError:
        return None
    return GPIO  # pragma: no cover


class DeterrentHandler:
    """Drives a BCM GPIO pin HIGH then LOW to simulate a trainer button press."""

    def __init__(self, config: DeterrentConfig) -> None:
        """Set up GPIO if enabled; self-disable on any failure."""
        self._config = config
        self._gpio: ModuleType | None = None
        self._enabled = config.enabled and self._setup()

    def _setup(self) -> bool:
        gpio = _import_gpio()
        if gpio is None:
            logger.warning('RPi.GPIO unavailable; deterrent handler disabled')
            return False
        try:
            gpio.setmode(gpio.BCM)
            gpio.setup(self._config.pin, gpio.OUT, initial=gpio.LOW)
        except Exception:
            logger.exception('GPIO setup failed; deterrent handler disabled')
            return False
        self._gpio = gpio
        return True

    def trigger(self, context: AlertContext) -> None:
        """Fire one timed burst: pin HIGH for burst_duration_seconds, then LOW."""
        if not self._enabled or self._gpio is None:
            return
        gpio = self._gpio
        pin = self._config.pin
        try:
            gpio.output(pin, gpio.HIGH)
            time.sleep(self._config.burst_duration_seconds)
        except Exception:
            logger.exception('Deterrent burst failed on pin %s', pin)
        finally:
            gpio.output(pin, gpio.LOW)

    def cleanup(self) -> None:
        """Release the GPIO resource; safe to call even if never set up."""
        if self._gpio is not None:
            self._gpio.cleanup()
            self._gpio = None
            self._enabled = False
