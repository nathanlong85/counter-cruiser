"""Tests for ZoneStore: reading zones with a version token."""

from __future__ import annotations

from counter_cruiser.client.web.zone_store import ZoneStore
from counter_cruiser.config.models import ClientSettings, Zone


def _zone(zone_id: str = 'z1') -> Zone:
    return Zone(id=zone_id, name='Counter', enabled=True, polygon=[(0, 0), (10, 0), (10, 10)])


class TestListZones:
    def test_empty_zone_set_returns_empty_list(self, tmp_path) -> None:
        config_path = tmp_path / 'client.toml'
        config_path.write_text('')
        store = ZoneStore(ClientSettings(zones=[]), config_path)
        zones, version = store.list_zones()
        assert zones == []
        assert isinstance(version, int)

    def test_returns_configured_zones(self, tmp_path) -> None:
        config_path = tmp_path / 'client.toml'
        config_path.write_text('')
        store = ZoneStore(ClientSettings(zones=[_zone()]), config_path)
        zones, _ = store.list_zones()
        assert zones == [_zone()]

    def test_version_is_config_file_mtime_ns(self, tmp_path) -> None:
        config_path = tmp_path / 'client.toml'
        config_path.write_text('')
        store = ZoneStore(ClientSettings(zones=[]), config_path)
        _, version = store.list_zones()
        assert version == config_path.stat().st_mtime_ns
