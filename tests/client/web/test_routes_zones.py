"""Tests for the zone-calibration HTTP endpoints."""

from __future__ import annotations

from counter_cruiser.client.web.app import create_app
from counter_cruiser.client.web.state import DashboardState
from counter_cruiser.client.web.zone_store import ZoneStore
from counter_cruiser.config.models import ClientSettings, Zone


def _zone_payload(zone_id: str = 'z1') -> dict:
    return {
        'id': zone_id,
        'name': 'Counter',
        'enabled': True,
        'polygon': [[0, 0], [10, 0], [10, 10]],
    }


def _client(tmp_path, zones=None):
    config_path = tmp_path / 'client.toml'
    config_path.write_text('')
    settings = ClientSettings(zones=zones or [])
    zone_store = ZoneStore(settings, config_path)
    app = create_app(DashboardState(), settings, zone_store)
    return app.test_client(), zone_store


class TestGetZones:
    def test_empty_zone_set(self, tmp_path) -> None:
        client, _ = _client(tmp_path)
        body = client.get('/api/zones').get_json()
        assert body['zones'] == []
        assert isinstance(body['version'], int)

    def test_returns_zone_fields(self, tmp_path) -> None:
        zone = Zone(**{k: v if k != 'polygon' else [tuple(p) for p in v] for k, v in _zone_payload().items()})
        client, _ = _client(tmp_path, zones=[zone])
        body = client.get('/api/zones').get_json()
        assert body['zones'] == [
            {'id': 'z1', 'name': 'Counter', 'enabled': True, 'polygon': [[0, 0], [10, 0], [10, 10]]}
        ]


class TestCreateZone:
    def test_valid_create_returns_201(self, tmp_path) -> None:
        client, _ = _client(tmp_path)
        version = client.get('/api/zones').get_json()['version']
        response = client.post('/api/zones', json={**_zone_payload(), 'version': version})
        assert response.status_code == 201

    def test_short_polygon_returns_400(self, tmp_path) -> None:
        client, _ = _client(tmp_path)
        version = client.get('/api/zones').get_json()['version']
        payload = {**_zone_payload(), 'polygon': [[0, 0], [1, 1]], 'version': version}
        response = client.post('/api/zones', json=payload)
        assert response.status_code == 400

    def test_stale_version_returns_409(self, tmp_path) -> None:
        client, _ = _client(tmp_path)
        response = client.post('/api/zones', json={**_zone_payload(), 'version': -1})
        assert response.status_code == 409

    def test_json_array_body_returns_400(self, tmp_path) -> None:
        client, _ = _client(tmp_path)
        response = client.post('/api/zones', json=[1, 2, 3])
        assert response.status_code == 400


class TestEditZone:
    def test_valid_edit_returns_200(self, tmp_path) -> None:
        zone = Zone(id='z1', name='Counter', enabled=True, polygon=[(0, 0), (10, 0), (10, 10)])
        client, _ = _client(tmp_path, zones=[zone])
        version = client.get('/api/zones').get_json()['version']
        response = client.put(
            '/api/zones/z1', json={'polygon': [[1, 1], [2, 1], [2, 2]], 'version': version}
        )
        assert response.status_code == 200

    def test_unknown_zone_returns_404(self, tmp_path) -> None:
        client, _ = _client(tmp_path)
        version = client.get('/api/zones').get_json()['version']
        response = client.put('/api/zones/unknown', json={'name': 'X', 'version': version})
        assert response.status_code == 404

    def test_stale_version_returns_409(self, tmp_path) -> None:
        zone = Zone(id='z1', name='Counter', enabled=True, polygon=[(0, 0), (10, 0), (10, 10)])
        client, _ = _client(tmp_path, zones=[zone])
        response = client.put('/api/zones/z1', json={'name': 'X', 'version': -1})
        assert response.status_code == 409

    def test_invalid_polygon_returns_400(self, tmp_path) -> None:
        zone = Zone(id='z1', name='Counter', enabled=True, polygon=[(0, 0), (10, 0), (10, 10)])
        client, _ = _client(tmp_path, zones=[zone])
        version = client.get('/api/zones').get_json()['version']
        response = client.put('/api/zones/z1', json={'polygon': [[1, 1]], 'version': version})
        assert response.status_code == 400

    def test_json_array_body_returns_400(self, tmp_path) -> None:
        zone = Zone(id='z1', name='Counter', enabled=True, polygon=[(0, 0), (10, 0), (10, 10)])
        client, _ = _client(tmp_path, zones=[zone])
        response = client.put('/api/zones/z1', json=[1, 2, 3])
        assert response.status_code == 400

    def test_toggle_enabled_preserves_polygon(self, tmp_path) -> None:
        original_polygon = [(0, 0), (10, 0), (10, 10)]
        zone = Zone(id='z1', name='Counter', enabled=True, polygon=original_polygon)
        client, _ = _client(tmp_path, zones=[zone])
        version = client.get('/api/zones').get_json()['version']
        response = client.put('/api/zones/z1', json={'enabled': False, 'version': version})
        assert response.status_code == 200
        body = response.get_json()
        assert body['enabled'] is False
        assert body['polygon'] == [[0, 0], [10, 0], [10, 10]]


class TestDeleteZone:
    def test_valid_delete_returns_200(self, tmp_path) -> None:
        zone = Zone(id='z1', name='Counter', enabled=True, polygon=[(0, 0), (10, 0), (10, 10)])
        client, _ = _client(tmp_path, zones=[zone])
        version = client.get('/api/zones').get_json()['version']
        response = client.delete(f'/api/zones/z1?version={version}')
        assert response.status_code == 200

    def test_unknown_zone_returns_404(self, tmp_path) -> None:
        client, _ = _client(tmp_path)
        version = client.get('/api/zones').get_json()['version']
        response = client.delete(f'/api/zones/unknown?version={version}')
        assert response.status_code == 404

    def test_stale_version_returns_409(self, tmp_path) -> None:
        zone = Zone(id='z1', name='Counter', enabled=True, polygon=[(0, 0), (10, 0), (10, 10)])
        client, _ = _client(tmp_path, zones=[zone])
        response = client.delete(f'/api/zones/z1?version=-1')
        assert response.status_code == 409
