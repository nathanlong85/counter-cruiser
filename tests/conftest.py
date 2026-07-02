"""Shared test fixtures."""

import numpy as np
import pytest

from counter_cruiser.config.models import Zone


@pytest.fixture()
def sample_frame() -> np.ndarray:
    """640x480 BGR frame filled with zeros (black)."""
    return np.zeros((480, 640, 3), dtype=np.uint8)


@pytest.fixture()
def full_frame_zone() -> Zone:
    """A zone that covers the entire 640x480 frame."""
    return Zone(
        id='counter',
        name='Counter',
        enabled=True,
        polygon=[(0, 0), (640, 0), (640, 480), (0, 480)],
    )
