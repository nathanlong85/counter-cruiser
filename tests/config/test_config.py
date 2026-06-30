"""Tests for configuration models and TOML loading."""
from __future__ import annotations

import os
from pathlib import Path

import pytest
from pydantic import ValidationError

from counter_cruiser.config.loader import load_client_config, load_server_config
from counter_cruiser.config.models import ClientSettings, ServerSettings, Zone


class TestZoneModel:
    def test_valid_zone_loads(self) -> None:
        z = Zone(id='z1', name='Counter', polygon=[(0, 0), (100, 0), (100, 100)])
        assert z.id == 'z1'
        assert z.enabled is True  # default

    def test_fewer_than_three_points_rejected(self) -> None:
        with pytest.raises(ValidationError, match='at least 3 points'):
            Zone(id='z1', name='Bad', polygon=[(0, 0), (1, 1)])

    def test_no_zones_config_is_valid(self) -> None:
        c = ClientSettings()
        assert c.zones == []


class TestClientSettings:
    def test_defaults_are_sensible(self) -> None:
        c = ClientSettings()
        assert c.server_host == 'localhost'
        assert c.server_port == 8765
        assert c.jpeg_quality == 85
        assert c.frame_skip == 3
        assert 0.0 <= c.min_size_ratio <= 1.0

    def test_jpeg_quality_out_of_range_rejected(self) -> None:
        with pytest.raises(ValidationError):
            ClientSettings(jpeg_quality=0)
        with pytest.raises(ValidationError):
            ClientSettings(jpeg_quality=101)

    def test_min_size_ratio_out_of_range_rejected(self) -> None:
        with pytest.raises(ValidationError):
            ClientSettings(min_size_ratio=-0.1)
        with pytest.raises(ValidationError):
            ClientSettings(min_size_ratio=1.1)

    def test_frame_skip_below_one_rejected(self) -> None:
        with pytest.raises(ValidationError):
            ClientSettings(frame_skip=0)

    def test_unknown_key_rejected(self) -> None:
        with pytest.raises(ValidationError):
            ClientSettings(nonexistent_key='boom')


class TestServerSettings:
    def test_defaults_are_sensible(self) -> None:
        s = ServerSettings()
        assert s.host == '0.0.0.0'
        assert s.port == 8765
        assert s.model_name == 'yolov8n.pt'
        assert s.device == 'auto'
        assert s.confidence_threshold == pytest.approx(0.5)

    def test_confidence_out_of_range_rejected(self) -> None:
        with pytest.raises(ValidationError):
            ServerSettings(confidence_threshold=1.5)

    def test_unknown_key_rejected(self) -> None:
        with pytest.raises(ValidationError):
            ServerSettings(mystery='field')


class TestTomlLoading:
    def test_load_from_explicit_path(self, tmp_path: Path) -> None:
        cfg = tmp_path / 'client.toml'
        cfg.write_text('[counter_cruiser]\nserver_port = 9999\n')
        result = load_client_config(cfg)
        assert result.server_port == 9999

    def test_missing_file_returns_defaults(self, tmp_path: Path) -> None:
        result = load_client_config(tmp_path / 'nonexistent.toml')
        assert result == ClientSettings()

    def test_env_var_overrides_file_value(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        cfg = tmp_path / 'client.toml'
        cfg.write_text('[counter_cruiser]\nserver_port = 9999\n')
        monkeypatch.setenv('COUNTER_CRUISER_SERVER_PORT', '7777')
        result = load_client_config(cfg)
        assert result.server_port == 7777

    def test_counter_cruiser_config_env_overrides_path(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        cfg = tmp_path / 'myconfig.toml'
        cfg.write_text('[counter_cruiser]\nserver_port = 5555\n')
        monkeypatch.setenv('COUNTER_CRUISER_CONFIG', str(cfg))
        result = load_client_config()  # no explicit path → env var path
        assert result.server_port == 5555

    def test_server_config_loads(self, tmp_path: Path) -> None:
        cfg = tmp_path / 'server.toml'
        cfg.write_text('[counter_cruiser]\nport = 9000\nconfidence_threshold = 0.7\n')
        result = load_server_config(cfg)
        assert result.port == 9000
        assert result.confidence_threshold == pytest.approx(0.7)

    def test_flat_toml_without_wrapper_table(self, tmp_path: Path) -> None:
        """TOML file without [counter_cruiser] wrapper is loaded directly."""
        cfg = tmp_path / 'client.toml'
        cfg.write_text('server_port = 8888\n')
        result = load_client_config(cfg)
        assert result.server_port == 8888

    def test_no_path_no_env_var_falls_back_to_default(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """When no explicit path and no env var, default path is used (absent → defaults)."""
        monkeypatch.delenv('COUNTER_CRUISER_CONFIG', raising=False)
        result = load_client_config()
        assert isinstance(result, ClientSettings)
