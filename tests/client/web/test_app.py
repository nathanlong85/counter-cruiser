"""Tests for the Flask app factory: builds a testable app from injected fakes."""

from __future__ import annotations

from counter_cruiser.client.web.app import create_app
from counter_cruiser.client.web.state import DashboardState
from counter_cruiser.config.models import ClientSettings


class FakeZoneStore:
    def list_zones(self):
        return [], 0


def test_create_app_returns_a_flask_instance() -> None:
    from flask import Flask

    app = create_app(DashboardState(), ClientSettings(), FakeZoneStore())
    assert isinstance(app, Flask)


def test_create_app_does_not_start_a_server() -> None:
    # Constructing the app must have no side effects beyond building routes;
    # if it did anything blocking, this test would hang.
    app = create_app(DashboardState(), ClientSettings(), FakeZoneStore())
    assert app is not None
