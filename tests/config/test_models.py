"""Tests for web configuration fields on ClientSettings."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from counter_cruiser.config.models import ClientSettings


def test_client_settings_web_defaults() -> None:
    settings = ClientSettings()
    assert settings.web_host == '0.0.0.0'
    assert settings.web_port == 8080
    assert settings.web_stream_fps == 5.0


def test_client_settings_rejects_non_positive_web_stream_fps() -> None:
    with pytest.raises(ValidationError):
        ClientSettings(web_stream_fps=0)
