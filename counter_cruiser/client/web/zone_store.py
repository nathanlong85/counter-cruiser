"""ZoneStore: read/write zones against ClientSettings with TOML persistence.

Mutates ``settings.zones`` in place so the running client sees edits
immediately, then writes the updated zone set back to the client TOML
config file. Optimistic concurrency: every mutating call must supply the
``version`` (the config file's mtime, in nanoseconds) it last read; a
mismatch means the file changed since the caller last read it.
"""

from __future__ import annotations

from pathlib import Path

from counter_cruiser.config.models import ClientSettings, Zone


class ZoneNotFoundError(Exception):
    """Raised when editing, toggling, or deleting an unknown zone id."""


class VersionConflictError(Exception):
    """Raised when a mutating request's version does not match the file's."""


class ZoneStore:
    """Injected collaborator giving the web UI read/write access to zones."""

    def __init__(self, settings: ClientSettings, config_path: Path) -> None:
        """Store the shared settings object and the file it should be persisted to."""
        self._settings = settings
        self._config_path = config_path

    def current_version(self) -> int:
        """Return the config file's current mtime in nanoseconds."""
        return self._config_path.stat().st_mtime_ns

    def list_zones(self) -> tuple[list[Zone], int]:
        """Return (current zones, current version)."""
        return list(self._settings.zones), self.current_version()

    def _check_version(self, version: int) -> None:  # pragma: no cover
        current = self.current_version()
        if version != current:
            raise VersionConflictError(
                f'config file changed since read (expected version {version}, got {current})'
            )

    def _find(self, zone_id: str) -> Zone:  # pragma: no cover
        for zone in self._settings.zones:
            if zone.id == zone_id:
                return zone
        raise ZoneNotFoundError(f'zone {zone_id!r} not found')
