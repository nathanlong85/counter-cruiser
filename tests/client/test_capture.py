"""Tests for camera capture interface and OpenCV implementation."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from counter_cruiser.client.capture import OpenCVCapture


class TestOpenCVCapture:
    @patch('counter_cruiser.client.capture.cv2')
    def test_open_succeeds_and_returns_actual_dims(self, mock_cv2: MagicMock) -> None:
        cap_mock = MagicMock()
        cap_mock.isOpened.return_value = True
        cap_mock.get.side_effect = lambda prop: {3: 640.0, 4: 480.0}.get(prop, 0.0)
        mock_cv2.VideoCapture.return_value = cap_mock
        mock_cv2.CAP_PROP_FRAME_WIDTH = 3
        mock_cv2.CAP_PROP_FRAME_HEIGHT = 4

        capture = OpenCVCapture()
        w, h = capture.open(index=0, width=640, height=480)

        assert w == 640
        assert h == 480
        cap_mock.set.assert_any_call(3, 640)
        cap_mock.set.assert_any_call(4, 480)

    @patch('counter_cruiser.client.capture.cv2')
    def test_open_failure_raises_runtime_error(self, mock_cv2: MagicMock) -> None:
        cap_mock = MagicMock()
        cap_mock.isOpened.return_value = False
        mock_cv2.VideoCapture.return_value = cap_mock

        capture = OpenCVCapture()
        with pytest.raises(RuntimeError, match='Cannot open camera'):
            capture.open(index=99, width=640, height=480)

    @patch('counter_cruiser.client.capture.cv2')
    def test_read_returns_frame_on_success(self, mock_cv2: MagicMock) -> None:
        cap_mock = MagicMock()
        cap_mock.isOpened.return_value = True
        cap_mock.get.return_value = 640.0
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        cap_mock.read.return_value = (True, frame)
        mock_cv2.VideoCapture.return_value = cap_mock
        mock_cv2.CAP_PROP_FRAME_WIDTH = 3
        mock_cv2.CAP_PROP_FRAME_HEIGHT = 4

        capture = OpenCVCapture()
        capture.open(0, 640, 480)
        result = capture.read()

        assert result is not None
        assert result.shape == (480, 640, 3)

    @patch('counter_cruiser.client.capture.cv2')
    def test_transient_read_failure_returns_none(self, mock_cv2: MagicMock) -> None:
        cap_mock = MagicMock()
        cap_mock.isOpened.return_value = True
        cap_mock.get.return_value = 640.0
        cap_mock.read.return_value = (False, None)
        mock_cv2.VideoCapture.return_value = cap_mock
        mock_cv2.CAP_PROP_FRAME_WIDTH = 3
        mock_cv2.CAP_PROP_FRAME_HEIGHT = 4

        capture = OpenCVCapture()
        capture.open(0, 640, 480)
        assert capture.read() is None

    @patch('counter_cruiser.client.capture.cv2')
    def test_release_closes_camera(self, mock_cv2: MagicMock) -> None:
        cap_mock = MagicMock()
        cap_mock.isOpened.return_value = True
        cap_mock.get.return_value = 640.0
        mock_cv2.VideoCapture.return_value = cap_mock
        mock_cv2.CAP_PROP_FRAME_WIDTH = 3
        mock_cv2.CAP_PROP_FRAME_HEIGHT = 4

        capture = OpenCVCapture()
        capture.open(0, 640, 480)
        capture.release()
        cap_mock.release.assert_called_once()

    def test_read_without_open_returns_none(self) -> None:
        """Reading from unopened capture returns None."""
        capture = OpenCVCapture()
        assert capture.read() is None

    def test_release_without_open_is_safe(self) -> None:
        """Releasing unopened capture is safe (idempotent)."""
        capture = OpenCVCapture()
        capture.release()  # Should not raise
