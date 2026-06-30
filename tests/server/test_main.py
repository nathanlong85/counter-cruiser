"""Tests for the server entrypoint module."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from unittest.mock import MagicMock, patch

from counter_cruiser.config.models import ServerSettings
from counter_cruiser.server.__main__ import _configure_logging, _serve, main


class TestConfigureLogging:
    """Tests for _configure_logging."""

    def test_configures_basic_logging(self) -> None:
        with patch('counter_cruiser.server.__main__.logging.basicConfig') as bc:
            _configure_logging()
        bc.assert_called_once()
        _, kwargs = bc.call_args
        assert kwargs['level'] == 20  # logging.INFO


class TestServe:
    """Tests for _serve, the async server bootstrap coroutine."""

    async def test_loads_config_model_and_serves(self) -> None:
        config = ServerSettings(
            host='127.0.0.1',
            port=9999,
            model_name='yolov8n.pt',
            device='auto',
            confidence_threshold=0.5,
        )

        @asynccontextmanager
        async def fake_serve(*args, **kwargs):
            yield MagicMock()

        with (
            patch(
                'counter_cruiser.server.__main__.load_server_config',
                return_value=config,
            ) as load_cfg,
            patch(
                'counter_cruiser.server.__main__.select_device',
                return_value='cpu',
            ) as select_dev,
            patch('counter_cruiser.server.__main__.YOLOAdapter') as yolo_cls,
            patch(
                'counter_cruiser.server.__main__.websockets.serve',
                side_effect=fake_serve,
            ) as ws_serve,
            patch(
                'counter_cruiser.server.__main__.asyncio.Future',
                side_effect=lambda: asyncio.sleep(0),
            ),
        ):
            await _serve()

        load_cfg.assert_called_once_with()
        select_dev.assert_called_once_with(config.device)
        yolo_cls.assert_called_once_with(
            config.model_name, 'cpu', config.confidence_threshold
        )
        ws_serve.assert_called_once()
        args, _ = ws_serve.call_args
        assert args[1] == config.host
        assert args[2] == config.port


class TestMain:
    """Tests for main(), the synchronous process entrypoint."""

    def test_configures_logging_and_runs_serve(self) -> None:
        with (
            patch(
                'counter_cruiser.server.__main__._configure_logging'
            ) as configure_logging,
            patch('counter_cruiser.server.__main__.asyncio.run') as run,
        ):
            main()

        configure_logging.assert_called_once_with()
        run.assert_called_once()
        run.call_args[0][0].close()  # silence "coroutine never awaited"
