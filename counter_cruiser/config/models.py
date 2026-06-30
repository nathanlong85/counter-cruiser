"""Pydantic-settings configuration models for client and server components."""
from __future__ import annotations

from pydantic import BaseModel, field_validator
from pydantic_settings import BaseSettings, PydanticBaseSettingsSource, SettingsConfigDict


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
    """Shared pydantic-settings base: env prefix, strict extras, env-over-init priority."""

    model_config = SettingsConfigDict(
        extra='forbid',
        env_prefix='COUNTER_CRUISER_',
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
