"""Structured alert-log handler: appends one JSON line per alert."""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime

from counter_cruiser.client.alerts.context import AlertContext
from counter_cruiser.config.models import LogConfig

logger = logging.getLogger(__name__)


class LogHandler:
    """Appends a structured JSON record to the configured log file per alert."""

    def __init__(self, config: LogConfig) -> None:
        """Store the target log file path."""
        self._config = config

    def trigger(self, context: AlertContext) -> None:
        """Append one JSON record; log and swallow any write failure."""
        record = {
            'timestamp': datetime.now(UTC).isoformat(),
            'triggered_zones': sorted(context.triggered_zones),
            'detection_count': len(context.detections),
            'frame_id': context.frame_id,
        }
        try:
            with open(self._config.file, 'a') as fh:
                fh.write(json.dumps(record) + '\n')
        except OSError:
            logger.exception('Failed to write alert log to %s', self._config.file)

    def cleanup(self) -> None:
        """No resources to release; each trigger opens and closes its own file."""
