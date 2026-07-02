"""AlertManager: per-zone cooldown and deterrent-first, isolated fan-out."""

from __future__ import annotations

import logging
import time

from counter_cruiser.client.alerts.context import AlertContext, AlertHandler

logger = logging.getLogger(__name__)


class AlertManager:
    """Enforces per-zone cooldown, then dispatches deterrent-first to handlers.

    The deterrent handler (if any) always runs before every other handler,
    so the training correction is never delayed by slower handlers (file
    writes, HTTP calls). Each handler's failure is isolated: one raising
    handler never prevents the others from running.
    """

    def __init__(
        self,
        handlers: list[AlertHandler],
        cooldown_seconds: float,
        deterrent: AlertHandler | None = None,
    ) -> None:
        """Store injected handlers and the per-zone cooldown window."""
        self._deterrent = deterrent
        self._handlers = handlers
        self._cooldown_seconds = cooldown_seconds
        self._last_alert: dict[str, float] = {}

    def _all_handlers(self) -> list[AlertHandler]:
        deterrent = [self._deterrent] if self._deterrent is not None else []
        return deterrent + self._handlers

    def _within_cooldown(self, zones: set[str], now: float) -> bool:
        if not zones:
            return False
        return all(
            now - self._last_alert.get(zone_id, float('-inf')) < self._cooldown_seconds
            for zone_id in zones
        )

    def maybe_alert(self, context: AlertContext) -> None:
        """Dispatch to all handlers unless every triggered zone is on cooldown."""
        now = time.monotonic()
        if self._within_cooldown(context.triggered_zones, now):
            logger.info(
                'Alert suppressed (cooldown): zones=%s',
                sorted(context.triggered_zones),
            )
            return
        for zone_id in context.triggered_zones:
            self._last_alert[zone_id] = now
        for handler in self._all_handlers():
            try:
                handler.trigger(context)
            except Exception:
                logger.exception('Alert handler %s failed', type(handler).__name__)

    def cleanup(self) -> None:
        """Clean up every handler, isolating one handler's cleanup failure."""
        for handler in self._all_handlers():
            try:
                handler.cleanup()
            except Exception:
                logger.exception(
                    'Cleanup failed for handler %s', type(handler).__name__
                )
