"""Pydantic-settings configuration models for client and server components."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, field_validator, model_validator
from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
)


class Zone(BaseModel):
    """A named polygon zone used for elevated-dog classification."""

    id: str
    name: str
    enabled: bool = True
    polygon: list[tuple[int, int]]

    @field_validator('polygon')
    @classmethod
    def at_least_three_points(cls, v: list[tuple[int, int]]) -> list[tuple[int, int]]:
        """Reject polygons with fewer than three vertices."""
        if len(v) < 3:
            raise ValueError('polygon must have at least 3 points')
        return v


class _BaseConfig(BaseSettings):
    """Shared pydantic-settings base: env prefix, strict extras, env-over-init."""

    model_config = SettingsConfigDict(
        extra='forbid',
        env_prefix='COUNTER_CRUISER_',
        env_nested_delimiter='__',
    )

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource | None = None,
        secrets_settings: PydanticBaseSettingsSource | None = None,
        **_kwargs: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        """Give env vars priority over init kwargs (TOML file values)."""
        return (env_settings, init_settings)


class DeterrentConfig(BaseModel):
    """GPIO deterrent settings: simulate a button press on the trainer."""

    model_config = ConfigDict(extra='forbid')

    enabled: bool = False
    pin: int | None = None
    burst_duration_seconds: float = 1.5
    stats_db_path: str = './deterrent_stats.db'

    @field_validator('burst_duration_seconds')
    @classmethod
    def positive_duration(cls, v: float) -> float:
        """Enforce a strictly positive burst duration."""
        if v <= 0:
            raise ValueError('burst_duration_seconds must be positive')
        return v

    @model_validator(mode='after')
    def pin_required_when_enabled(self) -> DeterrentConfig:
        """Reject enabled=True without a configured BCM pin."""
        if self.enabled and self.pin is None:
            raise ValueError('pin is required when deterrent is enabled')
        return self


class SnapshotConfig(BaseModel):
    """Annotated-snapshot recording settings."""

    model_config = ConfigDict(extra='forbid')

    enabled: bool = False
    dir: str = './snapshots'
    max_count: int = 200
    include_boxes: bool = True
    include_zones: bool = True

    @field_validator('max_count')
    @classmethod
    def positive_max_count(cls, v: int) -> int:
        """Enforce a strictly positive snapshot cap."""
        if v <= 0:
            raise ValueError('max_count must be positive')
        return v


class LogConfig(BaseModel):
    """Structured alert-log recording settings."""

    model_config = ConfigDict(extra='forbid')

    enabled: bool = False
    file: str = './alerts.log'


class NotificationConfig(BaseModel):
    """Push notification settings: config-selected provider + credentials."""

    model_config = ConfigDict(extra='forbid')

    enabled: bool = False
    provider: Literal['ntfy', 'pushover'] | None = None
    ntfy_topic: str | None = None
    pushover_user_key: str | None = None
    pushover_api_token: str | None = None


class AlertConfig(BaseModel):
    """Top-level alert settings: cooldown plus one group per handler."""

    model_config = ConfigDict(extra='forbid')

    cooldown_seconds: float = 5.0
    deterrent: DeterrentConfig = DeterrentConfig()
    snapshot: SnapshotConfig = SnapshotConfig()
    log: LogConfig = LogConfig()
    notification: NotificationConfig = NotificationConfig()

    @field_validator('cooldown_seconds')
    @classmethod
    def non_negative_cooldown(cls, v: float) -> float:
        """Enforce a non-negative cooldown window."""
        if v < 0:
            raise ValueError('cooldown_seconds must be >= 0')
        return v


class ClientSettings(_BaseConfig):
    """Configuration for the Pi-side client process."""

    server_host: str = 'localhost'
    server_port: int = 8765
    camera_index: int = 0
    frame_width: int = 640
    frame_height: int = 480
    jpeg_quality: int = 85
    frame_skip: int = 3
    min_size_ratio: float = 0.25
    zones: list[Zone] = []
    alerts: AlertConfig = AlertConfig()
    web_host: str = '0.0.0.0'
    web_port: int = 8080
    web_stream_fps: float = 5.0

    @field_validator('jpeg_quality')
    @classmethod
    def valid_jpeg_quality(cls, v: int) -> int:
        """Enforce JPEG quality range 1–100."""
        if not 1 <= v <= 100:
            raise ValueError('jpeg_quality must be between 1 and 100')
        return v

    @field_validator('min_size_ratio')
    @classmethod
    def valid_size_ratio(cls, v: float) -> float:
        """Enforce size ratio range 0.0–1.0."""
        if not 0.0 <= v <= 1.0:
            raise ValueError('min_size_ratio must be between 0.0 and 1.0')
        return v

    @field_validator('frame_skip')
    @classmethod
    def valid_frame_skip(cls, v: int) -> int:
        """Enforce frame_skip >= 1."""
        if v < 1:
            raise ValueError('frame_skip must be >= 1')
        return v

    @field_validator('web_stream_fps')
    @classmethod
    def positive_stream_fps(cls, v: float) -> float:
        """Enforce a strictly positive MJPEG stream frame rate."""
        if v <= 0:
            raise ValueError('web_stream_fps must be positive')
        return v


class ServerSettings(_BaseConfig):
    """Configuration for the inference server process."""

    host: str = '0.0.0.0'
    port: int = 8765
    model_name: str = 'yolov8n.pt'
    device: str = 'auto'
    confidence_threshold: float = 0.5

    @field_validator('confidence_threshold')
    @classmethod
    def valid_confidence(cls, v: float) -> float:
        """Enforce confidence threshold range 0.0–1.0."""
        if not 0.0 <= v <= 1.0:
            raise ValueError('confidence_threshold must be between 0.0 and 1.0')
        return v
