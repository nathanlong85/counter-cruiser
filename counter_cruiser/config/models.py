"""Configuration data models."""
from dataclasses import dataclass


@dataclass
class Zone:
    """Detection zone configuration."""

    id: str
    name: str
    enabled: bool
    polygon: list[tuple[int, int]]
