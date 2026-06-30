"""Tests for DetectionModel abstraction and device selection."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from counter_cruiser.server.model import DOG_CLASS_ID, YOLOAdapter, select_device
from counter_cruiser.shared.protocol import BoundingBox


def _make_yolo_result(
    x1: float, y1: float, x2: float, y2: float, conf: float, cls: int
) -> MagicMock:
    """Build a fake ultralytics result object."""
    box = MagicMock()
    box.xyxy = [MagicMock(__getitem__=lambda self, i: [x1, y1, x2, y2][i])]
    box.xyxy[0].__iter__ = lambda self: iter([x1, y1, x2, y2])
    box.conf = [conf]
    box.cls = [float(cls)]
    result = MagicMock()
    result.boxes = [box]
    return result


class TestYOLOAdapter:
    @patch('counter_cruiser.server.model.YOLO')
    def test_filters_to_dog_class_only(self, mock_yolo_cls: MagicMock) -> None:
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        mock_model = MagicMock()
        mock_yolo_cls.return_value = mock_model

        # Return one dog (class 16) and one cat (class 15)
        dog_result = _make_yolo_result(10, 20, 100, 200, 0.9, DOG_CLASS_ID)
        cat_result = _make_yolo_result(200, 200, 300, 300, 0.85, 15)
        combined = MagicMock()
        combined.boxes = dog_result.boxes + cat_result.boxes
        mock_model.return_value = [combined]

        adapter = YOLOAdapter('yolov8n.pt', 'cpu', confidence_threshold=0.5)
        boxes = adapter.detect(frame)
        assert len(boxes) == 1
        assert boxes[0].class_name == 'dog'

    @patch('counter_cruiser.server.model.YOLO')
    def test_excludes_below_threshold(self, mock_yolo_cls: MagicMock) -> None:
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        mock_model = MagicMock()
        mock_yolo_cls.return_value = mock_model

        low_conf = _make_yolo_result(10, 20, 100, 200, 0.3, DOG_CLASS_ID)
        mock_model.return_value = [low_conf]

        adapter = YOLOAdapter('yolov8n.pt', 'cpu', confidence_threshold=0.5)
        boxes = adapter.detect(frame)
        assert boxes == []

    @patch('counter_cruiser.server.model.YOLO')
    def test_maps_results_to_bounding_box(self, mock_yolo_cls: MagicMock) -> None:
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        mock_model = MagicMock()
        mock_yolo_cls.return_value = mock_model

        result = _make_yolo_result(10.0, 20.0, 100.0, 200.0, 0.9, DOG_CLASS_ID)
        mock_model.return_value = [result]

        adapter = YOLOAdapter('yolov8n.pt', 'cpu', confidence_threshold=0.5)
        boxes = adapter.detect(frame)
        assert len(boxes) == 1
        b = boxes[0]
        assert isinstance(b, BoundingBox)
        assert b.x1 == 10
        assert b.y2 == 200
        assert b.class_id == DOG_CLASS_ID


class TestSelectDevice:
    def test_explicit_device_returned_unchanged(self) -> None:
        assert select_device('cpu') == 'cpu'
        assert select_device('cuda:0') == 'cuda:0'
        assert select_device('mps') == 'mps'

    @patch('counter_cruiser.server.model.torch')
    def test_auto_picks_cuda_when_available(self, mock_torch: MagicMock) -> None:
        mock_torch.cuda.is_available.return_value = True
        assert select_device('auto') == 'cuda:0'

    @patch('counter_cruiser.server.model.torch')
    def test_auto_picks_mps_when_no_cuda(self, mock_torch: MagicMock) -> None:
        mock_torch.cuda.is_available.return_value = False
        mock_torch.backends.mps.is_available.return_value = True
        assert select_device('auto') == 'mps'

    @patch('counter_cruiser.server.model.torch')
    def test_auto_falls_back_to_cpu(self, mock_torch: MagicMock) -> None:
        mock_torch.cuda.is_available.return_value = False
        mock_torch.backends.mps.is_available.return_value = False
        assert select_device('auto') == 'cpu'
