"""Tests for the client entrypoint module."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from counter_cruiser.client.__main__ import _configure_logging, main
from counter_cruiser.config.models import ClientSettings
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
        config = ClientSettings()

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

        # Exercise the on_result closure to cover the zone-analysis/log branch.
        box = BoundingBox(
            x1=0, y1=0, x2=10, y2=400, confidence=0.9, class_id=16, class_name='dog'
        )
        msg = DetectionMessage(frame_id=1, boxes=[box], processing_time_ms=2.0)
        on_result(msg, 0.123)
