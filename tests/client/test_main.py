"""Tests for the client entrypoint module."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from counter_cruiser.client.__main__ import _configure_logging, _FpsTracker, main
from counter_cruiser.config.models import ClientSettings, Zone
from counter_cruiser.shared.protocol import BoundingBox, DetectionMessage


class TestConfigureLogging:
    """Tests for _configure_logging."""

    def test_configures_basic_logging(self) -> None:
        with patch('counter_cruiser.client.__main__.logging.basicConfig') as bc:
            _configure_logging()
        bc.assert_called_once()
        _, kwargs = bc.call_args
        assert kwargs['level'] == 20  # logging.INFO


class TestMain:
    """Tests for main(), the synchronous process entrypoint."""

    def test_wires_session_and_runs(self) -> None:
        zone = Zone(
            id='counter',
            name='Counter',
            polygon=[(0, 0), (640, 0), (640, 480), (0, 480)],
        )
        config = ClientSettings(zones=[zone])

        with (
            patch(
                'counter_cruiser.client.__main__._configure_logging'
            ) as configure_logging,
            patch(
                'counter_cruiser.client.__main__.load_client_config',
                return_value=config,
            ) as load_cfg,
            patch('counter_cruiser.client.__main__.OpenCVCapture') as capture_cls,
            patch('counter_cruiser.client.__main__.ClientSession') as session_cls,
            patch('counter_cruiser.client.__main__.signal.signal') as signal_signal,
            patch('counter_cruiser.client.__main__.asyncio.run') as run,
            patch('counter_cruiser.client.__main__.threading.Thread') as thread_cls,
        ):
            thread_cls.return_value = MagicMock()
            session_instance = MagicMock()
            session_instance.frame_height = config.frame_height
            # frame_id=1 -> no frame available yet; frame_id=2 -> a frame is
            # available, covering both branches of the `frame is not None`
            # check in on_result.
            fake_frame = MagicMock()
            session_instance.get_frame.side_effect = lambda frame_id: (
                None if frame_id == 1 else fake_frame
            )
            session_cls.return_value = session_instance

            main()

            configure_logging.assert_called_once_with()
            load_cfg.assert_called_once_with()
            capture_cls.assert_called_once_with()
            session_cls.assert_called_once()
            _, kwargs = session_cls.call_args
            assert kwargs['capture'] is capture_cls.return_value
            assert kwargs['config'] is config
            on_result = kwargs['on_result']

            assert signal_signal.call_count == 2
            run.assert_called_once_with(session_instance.run.return_value)

        # Exercise the on_result closure: single frame (debounce not met) —
        # no alert dispatch, but the zone-analysis/log branch is covered.
        box = BoundingBox(
            x1=0, y1=0, x2=10, y2=400, confidence=0.9, class_id=16, class_name='dog'
        )
        msg = DetectionMessage(frame_id=1, boxes=[box], processing_time_ms=2.0)
        on_result(msg, 0.123)

        # Second consecutive elevated frame: debounce satisfied, exercising
        # the alert-dispatch branch (AlertContext build + maybe_alert call).
        msg2 = DetectionMessage(frame_id=2, boxes=[box], processing_time_ms=2.0)
        on_result(msg2, 0.123)
        session_instance.get_frame.assert_called_with(2)

    def test_main_constructs_dashboard_state_and_starts_web_thread(
        self, monkeypatch
    ) -> None:
        """main() builds DashboardState + the Flask app and starts a daemon
        web thread, without ever starting real capture (asyncio.run mocked)."""
        started_threads = []

        class FakeThread:
            def __init__(self, target, args, daemon):
                self.target = target
                self.args = args
                self.daemon = daemon

            def start(self):
                started_threads.append(self)

        config = ClientSettings()

        with (
            patch('counter_cruiser.client.__main__._configure_logging'),
            patch(
                'counter_cruiser.client.__main__.load_client_config',
                return_value=config,
            ),
            patch('counter_cruiser.client.__main__.OpenCVCapture'),
            patch('counter_cruiser.client.__main__.ClientSession') as session_cls,
            monkeypatch.context() as m,
        ):
            session_cls.return_value.frame_height = config.frame_height
            m.setattr('counter_cruiser.client.__main__.threading.Thread', FakeThread)
            m.setattr('counter_cruiser.client.__main__.asyncio.run', lambda coro: None)
            m.setattr(
                'counter_cruiser.client.__main__.signal.signal', lambda *a, **k: None
            )

            main()

        assert len(started_threads) == 1
        assert started_threads[0].daemon is True


class TestFpsTracker:
    """Tests for _FpsTracker, a rolling-window FPS estimate."""

    def test_fewer_than_two_samples_returns_zero(self) -> None:
        clock = iter([0.0]).__next__
        tracker = _FpsTracker(clock=clock)
        assert tracker.tick() == 0.0

    def test_two_samples_half_second_apart_returns_two_fps(self) -> None:
        values = iter([0.0, 0.5])
        tracker = _FpsTracker(clock=lambda: next(values))
        tracker.tick()
        assert tracker.tick() == 2.0

    def test_samples_outside_window_are_evicted(self) -> None:
        values = iter([0.0, 1.0, 10.0])
        tracker = _FpsTracker(window_seconds=5.0, clock=lambda: next(values))
        tracker.tick()  # t=0.0
        tracker.tick()  # t=1.0 -> window [−4, 1], both kept, fps = 1/1.0 = 1.0
        fps = tracker.tick()  # t=10.0 -> cutoff=5.0, evicts t=0.0 and t=1.0
        assert fps == 0.0


class TestBuildAlertManager:
    def test_all_handlers_disabled_by_default(self) -> None:
        from counter_cruiser.client.__main__ import _build_alert_manager

        manager = _build_alert_manager(ClientSettings())
        # No handlers/deterrent constructed when everything is disabled.
        assert manager._handlers == []
        assert manager._deterrent is None

    def test_enabled_handlers_are_constructed(self) -> None:
        from counter_cruiser.client.__main__ import _build_alert_manager
        from counter_cruiser.config.models import (
            AlertConfig,
            LogConfig,
            NotificationConfig,
            SnapshotConfig,
        )

        config = ClientSettings(
            alerts=AlertConfig(
                log=LogConfig(enabled=True, file='alerts.log'),
                snapshot=SnapshotConfig(enabled=True),
                notification=NotificationConfig(enabled=True),
            )
        )
        manager = _build_alert_manager(config)
        assert len(manager._handlers) == 3


class TestMainCallsAlertManagerCleanupOnShutdown:
    def test_cleanup_called_after_run(self) -> None:
        config = ClientSettings()
        with (
            patch('counter_cruiser.client.__main__._configure_logging'),
            patch(
                'counter_cruiser.client.__main__.load_client_config',
                return_value=config,
            ),
            patch('counter_cruiser.client.__main__.OpenCVCapture'),
            patch('counter_cruiser.client.__main__.ClientSession') as session_cls,
            patch('counter_cruiser.client.__main__.signal.signal'),
            patch('counter_cruiser.client.__main__.asyncio.run'),
            patch('counter_cruiser.client.__main__.threading.Thread') as thread_cls,
            patch(
                'counter_cruiser.client.__main__._build_alert_manager'
            ) as build_manager,
        ):
            thread_cls.return_value = MagicMock()
            session_cls.return_value.frame_height = config.frame_height
            manager_instance = MagicMock()
            build_manager.return_value = manager_instance

            main()

            manager_instance.cleanup.assert_called_once_with()
