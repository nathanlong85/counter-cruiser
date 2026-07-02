"""Tests for the client entrypoint module."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from counter_cruiser.client.__main__ import _configure_logging, main
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
        ):
            session_instance = MagicMock()
            session_instance.frame_height = config.frame_height
            session_instance.get_frame.return_value = None
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
            patch(
                'counter_cruiser.client.__main__._build_alert_manager'
            ) as build_manager,
        ):
            session_cls.return_value.frame_height = config.frame_height
            manager_instance = MagicMock()
            build_manager.return_value = manager_instance

            main()

            manager_instance.cleanup.assert_called_once_with()
