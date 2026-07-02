"""Tests for ZoneStore: reading zones with a version token."""

from __future__ import annotations

import tomllib

import pytest

from counter_cruiser.client.web.zone_store import (
    VersionConflictError,
    ZoneNotFoundError,
    ZoneStore,
)
from counter_cruiser.config.models import ClientSettings, Zone


def _zone(zone_id: str = 'z1') -> Zone:
    return Zone(
        id=zone_id, name='Counter', enabled=True, polygon=[(0, 0), (10, 0), (10, 10)]
    )


def _store(tmp_path, zones=None):
    config_path = tmp_path / 'client.toml'
    config_path.write_text('')
    settings = ClientSettings(zones=zones or [])
    return ZoneStore(settings, config_path), config_path, settings


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


class TestCreateZone:
    def test_valid_create_adds_zone_and_persists(self, tmp_path) -> None:
        store, config_path, settings = _store(tmp_path)
        _, version = store.list_zones()
        store.create_zone(_zone(), version)
        assert settings.zones == [_zone()]
        on_disk = tomllib.loads(config_path.read_text())
        assert on_disk['zones'][0]['id'] == 'z1'

    def test_duplicate_id_is_rejected(self, tmp_path) -> None:
        store, _, _ = _store(tmp_path, zones=[_zone()])
        _, version = store.list_zones()
        with pytest.raises(ValueError, match='already exists'):
            store.create_zone(_zone(), version)

    def test_stale_version_is_rejected_without_writing(self, tmp_path) -> None:
        store, config_path, settings = _store(tmp_path)
        before = config_path.read_text()
        with pytest.raises(VersionConflictError):
            store.create_zone(_zone(), version=-1)
        assert settings.zones == []
        assert config_path.read_text() == before


class TestEditZone:
    def test_edit_polygon_replaces_it(self, tmp_path) -> None:
        store, _, settings = _store(tmp_path, zones=[_zone()])
        _, version = store.list_zones()
        new_polygon = [(1, 1), (2, 1), (2, 2)]
        store.edit_zone('z1', version, polygon=new_polygon)
        assert settings.zones[0].polygon == new_polygon

    def test_toggle_enabled_leaves_polygon_untouched(self, tmp_path) -> None:
        store, _, settings = _store(tmp_path, zones=[_zone()])
        _, version = store.list_zones()
        store.edit_zone('z1', version, enabled=False)
        assert settings.zones[0].enabled is False
        assert settings.zones[0].polygon == _zone().polygon

    def test_edit_with_short_polygon_is_rejected(self, tmp_path) -> None:
        store, _, settings = _store(tmp_path, zones=[_zone()])
        _, version = store.list_zones()
        with pytest.raises(ValueError):
            store.edit_zone('z1', version, polygon=[(0, 0), (1, 1)])
        assert settings.zones[0].polygon == _zone().polygon

    def test_edit_unknown_zone_raises_not_found(self, tmp_path) -> None:
        store, _, _ = _store(tmp_path, zones=[_zone()])
        _, version = store.list_zones()
        with pytest.raises(ZoneNotFoundError):
            store.edit_zone('unknown', version, name='X')

    def test_edit_name_replaces_it(self, tmp_path) -> None:
        store, _, settings = _store(tmp_path, zones=[_zone()])
        _, version = store.list_zones()
        store.edit_zone('z1', version, name='Renamed')
        assert settings.zones[0].name == 'Renamed'
        assert settings.zones[0].polygon == _zone().polygon


class TestDeleteZone:
    def test_delete_removes_zone_and_persists(self, tmp_path) -> None:
        store, config_path, settings = _store(tmp_path, zones=[_zone()])
        _, version = store.list_zones()
        store.delete_zone('z1', version)
        assert settings.zones == []
        on_disk = tomllib.loads(config_path.read_text())
        assert on_disk.get('zones', []) == []

    def test_delete_unknown_zone_raises_not_found(self, tmp_path) -> None:
        store, _, _ = _store(tmp_path)
        _, version = store.list_zones()
        with pytest.raises(ZoneNotFoundError):
            store.delete_zone('unknown', version)


class TestPersistenceRoundTrip:
    def test_persisted_zones_reload_identically(self, tmp_path) -> None:
        store, config_path, settings = _store(tmp_path)
        _, version = store.list_zones()
        store.create_zone(_zone(), version)
        reloaded = ClientSettings(**tomllib.loads(config_path.read_text()))
        assert reloaded.zones == settings.zones

    def test_write_is_atomic_no_leftover_temp_files(self, tmp_path) -> None:
        store, config_path, _ = _store(tmp_path)
        _, version = store.list_zones()
        store.create_zone(_zone(), version)
        leftovers = [p for p in tmp_path.iterdir() if p != config_path]
        assert leftovers == []

    def test_wrapper_table_config_preserves_other_settings(self, tmp_path) -> None:
        config_path = tmp_path / 'client.toml'
        config_path.write_text('[counter_cruiser]\nserver_host = "192.168.1.50"\n')
        settings = ClientSettings(server_host='192.168.1.50', zones=[])
        store = ZoneStore(settings, config_path)
        _, version = store.list_zones()
        store.create_zone(_zone(), version)
        on_disk = tomllib.loads(config_path.read_text())
        assert on_disk['counter_cruiser']['server_host'] == '192.168.1.50'
        assert on_disk['counter_cruiser']['zones'][0]['id'] == 'z1'

    def test_write_failure_removes_temp_file_and_reraises(
        self, tmp_path, monkeypatch
    ) -> None:
        store, config_path, _ = _store(tmp_path)
        _, version = store.list_zones()

        def _boom(*args, **kwargs):
            raise OSError('disk full')

        monkeypatch.setattr('os.replace', _boom)
        with pytest.raises(OSError, match='disk full'):
            store.create_zone(_zone(), version)
        leftovers = [p for p in tmp_path.iterdir() if p != config_path]
        assert leftovers == []
