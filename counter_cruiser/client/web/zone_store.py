"""ZoneStore: read/write zones against ClientSettings with TOML persistence.

Mutates ``settings.zones`` in place so the running client sees edits
immediately, then writes the updated zone set back to the client TOML
config file. Optimistic concurrency: every mutating call must supply the
``version`` (the config file's mtime, in nanoseconds) it last read; a
mismatch means the file changed since the caller last read it.
"""

from __future__ import annotations

import contextlib
import os
import tempfile
from pathlib import Path

import tomlkit

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

    def _check_version(self, version: int) -> None:
        current = self.current_version()
        if version != current:
            raise VersionConflictError(
                f'config file changed since read (expected version {version}, got {current})'
            )

    def _find(self, zone_id: str) -> Zone:
        for zone in self._settings.zones:
            if zone.id == zone_id:
                return zone
        raise ZoneNotFoundError(f'zone {zone_id!r} not found')

    def create_zone(self, zone: Zone, version: int) -> None:
        """Add *zone*; rejects duplicate ids or a stale *version*."""
        self._check_version(version)
        if any(existing.id == zone.id for existing in self._settings.zones):
            raise ValueError(f'zone {zone.id!r} already exists')
        self._settings.zones.append(zone)
        self._write_toml()

    def edit_zone(
        self,
        zone_id: str,
        version: int,
        *,
        name: str | None = None,
        polygon: list[tuple[int, int]] | None = None,
        enabled: bool | None = None,
    ) -> None:
        """Apply a partial update to an existing zone; validates before mutating.

        Only the given (non-None) fields change. Re-validates the resulting
        zone through the :class:`Zone` model before touching the in-memory
        list or the file, so an invalid polygon leaves both unchanged.
        """
        self._check_version(version)
        existing = self._find(zone_id)
        data = existing.model_dump()
        if name is not None:
            data['name'] = name
        if polygon is not None:
            data['polygon'] = polygon
        if enabled is not None:
            data['enabled'] = enabled
        updated = Zone(**data)  # raises ValueError (pydantic) on invalid polygon
        idx = self._settings.zones.index(existing)
        self._settings.zones[idx] = updated
        self._write_toml()

    def delete_zone(self, zone_id: str, version: int) -> None:
        """Remove an existing zone; rejects an unknown id or a stale *version*."""
        self._check_version(version)
        existing = self._find(zone_id)
        self._settings.zones.remove(existing)
        self._write_toml()

    def _write_toml(self) -> None:
        """Atomically rewrite only the zones section of the config file.

        Loads the document with tomlkit (preserving comments/formatting
        elsewhere), replaces the zones array-of-tables under the optional
        ``[counter_cruiser]`` wrapper table (or the top level if unwrapped),
        and writes via temp-file-then-rename so a crash mid-write cannot
        corrupt the file.
        """
        if self._config_path.exists() and self._config_path.stat().st_size > 0:
            with open(self._config_path, encoding='utf-8') as fh:
                doc = tomlkit.load(fh)
        else:
            doc = tomlkit.document()
        target = doc.get('counter_cruiser', doc)
        zones_array = tomlkit.aot()
        for zone in self._settings.zones:
            item = tomlkit.table()
            item['id'] = zone.id
            item['name'] = zone.name
            item['enabled'] = zone.enabled
            item['polygon'] = [list(point) for point in zone.polygon]
            zones_array.append(item)
        target['zones'] = zones_array

        fd, tmp_name = tempfile.mkstemp(dir=self._config_path.parent, suffix='.tmp')
        try:
            with os.fdopen(fd, 'w', encoding='utf-8') as fh:
                fh.write(tomlkit.dumps(doc))
            os.replace(tmp_name, self._config_path)
        except BaseException:
            with contextlib.suppress(OSError):
                os.remove(tmp_name)
            raise
