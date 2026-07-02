"""Encapsulated, injected UI state: frame, detections, stats, alert history.

Replaces module-level globals with a single thread-safe object. The client's
result callback writes; Flask request handlers read. All writes and reads
take a single internal lock; frames are copy-on-read to avoid tearing.
"""

from __future__ import annotations

import threading
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime

import numpy as np

from counter_cruiser.shared.protocol import BoundingBox

_DEFAULT_ALERT_HISTORY_CAPACITY = 50


@dataclass(frozen=True)
class DetectionSnapshot:
    """Point-in-time detection result."""

    detections: list[BoundingBox] = field(default_factory=list)
    triggered_zones: set[str] = field(default_factory=set)
    elevated: bool = False


@dataclass(frozen=True)
class StatsSnapshot:
    """Point-in-time pipeline stats."""

    fps: float = 0.0
    latency_ms: float = 0.0
    server_connected: bool = False


@dataclass(frozen=True)
class AlertHistoryEntry:
    """One recorded alert event for the dashboard's history list."""

    time: datetime
    triggered_zones: frozenset[str]
    frame_id: int


class DashboardState:
    """Thread-safe holder for the web UI's view of the running client.

    Constructed once at entrypoint and injected into ``create_app``. The
    client thread calls the ``update_*``/``record_alert`` methods; Flask
    request handlers (running in a different thread) call the ``get_*``
    methods.
    """

    def __init__(self, alert_history_capacity: int = _DEFAULT_ALERT_HISTORY_CAPACITY) -> None:
        """Initialise empty frame/detection/stats state and an empty history."""
        self._lock = threading.Lock()
        self._frame: np.ndarray | None = None
        self._detection = DetectionSnapshot()
        self._stats = StatsSnapshot()
        self._alerts: deque[AlertHistoryEntry] = deque(maxlen=alert_history_capacity)

    def update_frame(self, frame: np.ndarray) -> None:
        """Store a copy of the latest captured frame."""
        with self._lock:
            self._frame = frame.copy()

    def get_frame(self) -> np.ndarray | None:
        """Return a copy of the latest frame, or None if none captured yet."""
        with self._lock:
            return None if self._frame is None else self._frame.copy()

    def update_detection(
        self, detections: list[BoundingBox], triggered_zones: set[str], elevated: bool
    ) -> None:
        """Store the latest detection result."""
        with self._lock:
            self._detection = DetectionSnapshot(
                detections=list(detections),
                triggered_zones=set(triggered_zones),
                elevated=elevated,
            )

    def get_detection(self) -> DetectionSnapshot:
        """Return the latest detection snapshot."""
        with self._lock:
            return self._detection

    def update_stats(self, fps: float, latency_ms: float, server_connected: bool) -> None:
        """Store the latest pipeline stats."""
        with self._lock:
            self._stats = StatsSnapshot(
                fps=fps, latency_ms=latency_ms, server_connected=server_connected
            )

    def get_stats(self) -> StatsSnapshot:
        """Return the latest stats snapshot."""
        with self._lock:
            return self._stats

    def record_alert(self, entry: AlertHistoryEntry) -> None:
        """Append *entry* to the bounded alert history (newest at the front)."""
        with self._lock:
            self._alerts.appendleft(entry)

    def get_alerts(self) -> list[AlertHistoryEntry]:
        """Return recorded alerts, newest first, bounded to the configured capacity."""
        with self._lock:
            return list(self._alerts)
