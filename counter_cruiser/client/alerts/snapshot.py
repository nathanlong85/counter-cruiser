"""Snapshot handler: annotated JPEG + JSON metadata sidecar, max-count cleanup."""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from pathlib import Path

import cv2

from counter_cruiser.client.alerts.context import AlertContext
from counter_cruiser.client.annotation import annotate_frame
from counter_cruiser.config.models import SnapshotConfig

logger = logging.getLogger(__name__)


class SnapshotHandler:
    """Writes an annotated JPEG and a JSON sidecar for each triggered alert."""

    def __init__(self, config: SnapshotConfig) -> None:
        """Ensure the snapshot directory exists."""
        self._config = config
        Path(config.dir).mkdir(parents=True, exist_ok=True)

    def trigger(self, context: AlertContext) -> None:
        """Save an annotated snapshot + sidecar, or log and skip if no frame."""
        if context.frame is None:
            logger.warning(
                'No frame retained for frame_id=%s; skipping snapshot',
                context.frame_id,
            )
            return
        annotated = annotate_frame(
            context.frame,
            context.detections,
            context.zones,
            context.triggered_zones,
            include_boxes=self._config.include_boxes,
            include_zones=self._config.include_zones,
        )
        now = datetime.now(UTC)
        stem = f'{now.strftime("%Y%m%dT%H%M%S%f")}_frame{context.frame_id}'
        image_path = Path(self._config.dir) / f'{stem}.jpg'
        sidecar_path = Path(self._config.dir) / f'{stem}.json'
        cv2.imwrite(str(image_path), annotated)
        sidecar_path.write_text(
            json.dumps(
                {
                    'timestamp': now.isoformat(),
                    'triggered_zones': sorted(context.triggered_zones),
                    'detection_count': len(context.detections),
                    'frame_id': context.frame_id,
                }
            )
        )
        self._enforce_max_count()

    def _enforce_max_count(self) -> None:
        images = sorted(Path(self._config.dir).glob('*.jpg'))
        excess = len(images) - self._config.max_count
        for image_path in images[: max(excess, 0)]:
            image_path.unlink(missing_ok=True)
            image_path.with_suffix('.json').unlink(missing_ok=True)

    def cleanup(self) -> None:
        """No resources to release; each trigger opens and closes its own files."""
