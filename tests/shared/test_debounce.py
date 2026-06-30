"""Tests for consecutive-detection debouncing."""
import pytest

from counter_cruiser.shared.debounce import DetectionHistory


class TestDetectionHistory:
    def test_two_consecutive_elevated_meets_condition(self) -> None:
        h = DetectionHistory()
        h.add(1, is_elevated=True)
        h.add(2, is_elevated=True)
        assert h.is_consecutive_elevated() is True

    def test_single_elevated_does_not_meet_condition(self) -> None:
        h = DetectionHistory()
        h.add(1, is_elevated=True)
        assert h.is_consecutive_elevated() is False

    def test_elevated_frames_too_far_apart_do_not_meet(self) -> None:
        h = DetectionHistory()
        h.add(1, is_elevated=True)
        h.add(10, is_elevated=True)  # gap=9 > max_gap=2
        assert h.is_consecutive_elevated() is False

    def test_elevated_within_max_gap_meets(self) -> None:
        h = DetectionHistory()
        h.add(1, is_elevated=True)
        h.add(3, is_elevated=True)  # gap=2 == max_gap → meets condition
        assert h.is_consecutive_elevated() is True

    def test_out_of_order_results_evaluated_by_frame_id(self) -> None:
        h = DetectionHistory()
        h.add(5, is_elevated=True)
        h.add(3, is_elevated=True)  # added after but frame_id=3 < 5 → gap=2 → meets
        assert h.is_consecutive_elevated() is True

    def test_history_is_bounded(self) -> None:
        h = DetectionHistory(max_size=5)
        for i in range(10):
            h.add(i, is_elevated=False)
        assert len(h._records) == 5

    def test_oldest_entries_discarded_when_bounded(self) -> None:
        h = DetectionHistory(max_size=3)
        for i in range(5):
            h.add(i, is_elevated=False)
        # Only frames 2,3,4 should remain
        frame_ids = [r.frame_id for r in h._records]
        assert frame_ids == [2, 3, 4]

    def test_non_elevated_frames_between_elevated_still_meets(self) -> None:
        h = DetectionHistory()
        h.add(1, is_elevated=True)
        h.add(2, is_elevated=False)
        h.add(3, is_elevated=True)  # gap between elevated[0] and elevated[1] = 2 → meets
        assert h.is_consecutive_elevated() is True
