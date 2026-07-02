"""Tests for configuration models and TOML loading."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from counter_cruiser.config.loader import (
    load_client_config,
    load_server_config,
    resolve_client_config_path,
)
from counter_cruiser.config.models import (
    AlertConfig,
    ClientSettings,
    DeterrentConfig,
    LogConfig,
    NotificationConfig,
    ServerSettings,
    SnapshotConfig,
    Zone,
)


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

    def test_env_var_overrides_file_value(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
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
        """No explicit path, no env var → default path used (absent → defaults)."""
        monkeypatch.delenv('COUNTER_CRUISER_CONFIG', raising=False)
        result = load_client_config()
        assert isinstance(result, ClientSettings)

    def test_full_alert_section_round_trips(self, tmp_path: Path) -> None:
        cfg = tmp_path / 'client.toml'
        cfg.write_text(
            '[counter_cruiser.alerts]\n'
            'cooldown_seconds = 5\n'
            '[counter_cruiser.alerts.deterrent]\n'
            'enabled = true\n'
            'pin = 17\n'
            'burst_duration_seconds = 1.5\n'
            '[counter_cruiser.alerts.snapshot]\n'
            'enabled = true\n'
            'dir = "./snapshots"\n'
            'max_count = 200\n'
            '[counter_cruiser.alerts.log]\n'
            'enabled = true\n'
            'file = "./alerts.log"\n'
            '[counter_cruiser.alerts.notification]\n'
            'enabled = true\n'
            'provider = "ntfy"\n'
            'ntfy_topic = "counter-cruiser-alerts"\n'
        )
        result = load_client_config(cfg)
        assert result.alerts.deterrent.pin == 17
        assert result.alerts.notification.ntfy_topic == 'counter-cruiser-alerts'


class TestDeterrentConfig:
    def test_defaults(self) -> None:
        c = DeterrentConfig()
        assert c.enabled is False
        assert c.pin is None
        assert c.burst_duration_seconds == pytest.approx(1.5)

    def test_pin_required_when_enabled(self) -> None:
        with pytest.raises(ValidationError, match='pin'):
            DeterrentConfig(enabled=True)

    def test_pin_optional_when_disabled(self) -> None:
        c = DeterrentConfig(enabled=False)
        assert c.pin is None

    def test_enabled_with_pin_is_valid(self) -> None:
        c = DeterrentConfig(enabled=True, pin=17)
        assert c.pin == 17

    def test_non_positive_burst_duration_rejected(self) -> None:
        with pytest.raises(ValidationError):
            DeterrentConfig(enabled=True, pin=17, burst_duration_seconds=0)
        with pytest.raises(ValidationError):
            DeterrentConfig(enabled=True, pin=17, burst_duration_seconds=-1.0)

    def test_unknown_key_rejected(self) -> None:
        with pytest.raises(ValidationError):
            DeterrentConfig(frequency=20000)


class TestSnapshotConfig:
    def test_defaults(self) -> None:
        c = SnapshotConfig()
        assert c.enabled is False
        assert c.dir == './snapshots'
        assert c.max_count == 200
        assert c.include_boxes is True
        assert c.include_zones is True

    def test_non_positive_max_count_rejected(self) -> None:
        with pytest.raises(ValidationError):
            SnapshotConfig(max_count=0)

    def test_unknown_key_rejected(self) -> None:
        with pytest.raises(ValidationError):
            SnapshotConfig(bogus=True)


class TestLogConfig:
    def test_defaults(self) -> None:
        c = LogConfig()
        assert c.enabled is False
        assert c.file == './alerts.log'

    def test_unknown_key_rejected(self) -> None:
        with pytest.raises(ValidationError):
            LogConfig(path='x')


class TestNotificationConfig:
    def test_defaults(self) -> None:
        c = NotificationConfig()
        assert c.enabled is False
        assert c.provider is None

    def test_provider_restricted_to_supported_values(self) -> None:
        NotificationConfig(provider='ntfy')
        NotificationConfig(provider='pushover')
        with pytest.raises(ValidationError):
            NotificationConfig(provider='telegram')

    def test_unknown_key_rejected(self) -> None:
        with pytest.raises(ValidationError):
            NotificationConfig(email='x@example.com')


class TestAlertConfig:
    def test_defaults(self) -> None:
        c = AlertConfig()
        assert c.cooldown_seconds == pytest.approx(5.0)
        assert isinstance(c.deterrent, DeterrentConfig)
        assert isinstance(c.snapshot, SnapshotConfig)
        assert isinstance(c.log, LogConfig)
        assert isinstance(c.notification, NotificationConfig)

    def test_negative_cooldown_rejected(self) -> None:
        with pytest.raises(ValidationError):
            AlertConfig(cooldown_seconds=-1.0)

    def test_unknown_key_rejected(self) -> None:
        with pytest.raises(ValidationError):
            AlertConfig(bogus=1)


class TestClientSettingsAlerts:
    def test_alerts_default_to_disabled(self) -> None:
        c = ClientSettings()
        assert c.alerts.deterrent.enabled is False
        assert c.alerts.snapshot.enabled is False
        assert c.alerts.log.enabled is False
        assert c.alerts.notification.enabled is False

    def test_env_override_for_nested_alert_field(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv('COUNTER_CRUISER_ALERTS__COOLDOWN_SECONDS', '10')
        c = ClientSettings()
        assert c.alerts.cooldown_seconds == pytest.approx(10.0)

    def test_alerts_from_toml(self, tmp_path) -> None:
        cfg = tmp_path / 'client.toml'
        cfg.write_text(
            '[counter_cruiser.alerts]\ncooldown_seconds = 7\n'
            '[counter_cruiser.alerts.deterrent]\nenabled = true\npin = 27\n'
        )
        result = load_client_config(cfg)
        assert result.alerts.cooldown_seconds == pytest.approx(7.0)
        assert result.alerts.deterrent.enabled is True
        assert result.alerts.deterrent.pin == 27


def test_resolve_client_config_path_uses_explicit_argument(tmp_path) -> None:
    explicit = tmp_path / 'my.toml'
    assert resolve_client_config_path(explicit) == explicit


def test_resolve_client_config_path_falls_back_to_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv('COUNTER_CRUISER_CONFIG', raising=False)
    assert resolve_client_config_path() == Path('config/client.toml')
