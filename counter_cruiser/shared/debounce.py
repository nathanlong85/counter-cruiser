"""Consecutive-detection debouncing for the zone-analysis pipeline."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class FrameRecord:
    """A single frame's elevated classification result."""

    frame_id: int
    is_elevated: bool


class DetectionHistory:
    """Bounded sliding window of recent frame results.

    Considers the elevated state actionable only when at least two elevated
    frames appear within *max_gap* frame-id distance, tolerating non-elevated
    frames between them.
    """

    def __init__(self, max_size: int = 20) -> None:
        """Create history with a fixed maximum capacity."""
        self._records: list[FrameRecord] = []
        self._max_size = max_size

    def add(self, frame_id: int, is_elevated: bool) -> None:
        """Record the result for *frame_id*, discarding oldest if at capacity."""
        self._records.append(FrameRecord(frame_id=frame_id, is_elevated=is_elevated))
        if len(self._records) > self._max_size:
            self._records = self._records[-self._max_size :]

    def is_consecutive_elevated(self, max_gap: int = 2) -> bool:
        """Return True if any two elevated frames in history have frame-id gap <= max_gap."""
        elevated = sorted(
            (r for r in self._records if r.is_elevated),
            key=lambda r: r.frame_id,
        )
        if len(elevated) < 2:
            return False
        return any(
            elevated[i + 1].frame_id - elevated[i].frame_id <= max_gap
            for i in range(len(elevated) - 1)
        )
