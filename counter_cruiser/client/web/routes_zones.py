"""Zone-calibration HTTP endpoints: CRUD over ZoneStore with error mapping."""

from __future__ import annotations

from flask import Flask, jsonify, request
from pydantic import ValidationError

from counter_cruiser.client.web.zone_store import (
    VersionConflictError,
    ZoneNotFoundError,
    ZoneStore,
)
from counter_cruiser.config.models import Zone


def _zone_to_dict(zone: Zone) -> dict:
    return {
        'id': zone.id,
        'name': zone.name,
        'enabled': zone.enabled,
        'polygon': [list(point) for point in zone.polygon],
    }


def register_zone_routes(app: Flask, zone_store: ZoneStore) -> None:
    """Register the zone CRUD endpoints on *app*."""

    @app.get('/api/zones')
    def get_zones():
        zones, version = zone_store.list_zones()
        return jsonify({'zones': [_zone_to_dict(z) for z in zones], 'version': version})

    @app.post('/api/zones')
    def create_zone():
        body = request.get_json()
        try:
            zone = Zone(
                id=body['id'],
                name=body['name'],
                enabled=body.get('enabled', True),
                polygon=[tuple(point) for point in body['polygon']],
            )
            zone_store.create_zone(zone, body['version'])
        except VersionConflictError as exc:
            return jsonify({'error': str(exc)}), 409
        except (ValidationError, ValueError, KeyError) as exc:
            return jsonify({'error': str(exc)}), 400
        return jsonify(_zone_to_dict(zone)), 201

    @app.put('/api/zones/<zone_id>')
    def edit_zone(zone_id: str):
        body = request.get_json()
        try:
            zone_store.edit_zone(
                zone_id,
                body['version'],
                name=body.get('name'),
                polygon=[tuple(point) for point in body['polygon']] if 'polygon' in body else None,
                enabled=body.get('enabled'),
            )
        except VersionConflictError as exc:
            return jsonify({'error': str(exc)}), 409
        except ZoneNotFoundError as exc:
            return jsonify({'error': str(exc)}), 404
        except (ValidationError, ValueError, KeyError) as exc:
            return jsonify({'error': str(exc)}), 400
        zones, _ = zone_store.list_zones()
        updated = next(z for z in zones if z.id == zone_id)
        return jsonify(_zone_to_dict(updated)), 200

    @app.delete('/api/zones/<zone_id>')
    def delete_zone(zone_id: str):
        version = request.args.get('version', type=int)
        try:
            zone_store.delete_zone(zone_id, version)
        except VersionConflictError as exc:
            return jsonify({'error': str(exc)}), 409
        except ZoneNotFoundError as exc:
            return jsonify({'error': str(exc)}), 404
        return jsonify({'deleted': zone_id}), 200
