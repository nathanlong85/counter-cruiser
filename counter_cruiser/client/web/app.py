"""Flask application factory for the web UI.

No module-level mutable state: every route handler closes over the injected
``DashboardState``, ``ClientSettings``, and ``ZoneStore`` passed to
``create_app``. Route registration lives in sibling modules; this module
only assembles them.
"""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from flask import Flask

from counter_cruiser.client.web.routes_dashboard import register_dashboard_routes
from counter_cruiser.client.web.routes_live_feed import register_live_feed_routes
from counter_cruiser.client.web.routes_zones import register_zone_routes
from counter_cruiser.client.web.state import DashboardState
from counter_cruiser.config.models import ClientSettings, Zone

_TEMPLATES_DIR = Path(__file__).parent / 'templates'


class ZoneStoreProtocol(Protocol):
    """Structural interface the app factory depends on for zone routes."""

    def list_zones(self) -> tuple[list[Zone], int]:
        """Return (zones, version)."""
        ...  # pragma: no cover


def create_app(
    state: DashboardState, settings: ClientSettings, zone_store: ZoneStoreProtocol
) -> Flask:
    """Build and return a Flask app wired to the injected collaborators."""
    app = Flask(__name__, template_folder=str(_TEMPLATES_DIR))
    _register_all_routes(app, state, settings, zone_store)
    return app


def _register_all_routes(
    app: Flask, state: DashboardState, settings: ClientSettings, zone_store: ZoneStoreProtocol
) -> None:
    """Register every route module's handlers on *app*.

    Split out so later tasks can add a `register_*_routes` call each without
    growing `create_app` itself — each import is added by the task that
    introduces the corresponding route module.
    """
    register_dashboard_routes(app, state)
    register_live_feed_routes(app, state, settings)
    register_zone_routes(app, zone_store)
