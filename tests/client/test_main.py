"""Tests for the client entrypoint module."""

from __future__ import annotations

import socket
import threading
import time
from unittest.mock import MagicMock, patch

import requests

from counter_cruiser.client.__main__ import (
    _configure_logging,
    _FpsTracker,
    _run_web_server,
    main,
)
from counter_cruiser.client.web.app import create_app
from counter_cruiser.client.web.state import DashboardState
from counter_cruiser.client.web.zone_store import ZoneStore
from counter_cruiser.config.models import (
    AlertConfig,
    ClientSettings,
    DeterrentConfig,
    Zone,
)
from counter_cruiser.shared.protocol import BoundingBox, DetectionMessage


class FakeStatsStore:
    """Minimal stand-in for the deterrent stats store in tests."""

    def recent_events(self, since_days: int):
        return []

    def recent_failures(self, limit: int):
        return []


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

    def test_wires_session_and_runs(self, tmp_path) -> None:
        zone = Zone(
            id='counter',
            name='Counter',
            polygon=[(0, 0), (640, 0), (640, 480), (0, 480)],
        )
        config = ClientSettings(
            zones=[zone],
            alerts=AlertConfig(
                deterrent=DeterrentConfig(stats_db_path=str(tmp_path / 'stats.db'))
            ),
        )
        config_path = tmp_path / 'client.toml'
        config_path.write_text('')

        real_state = DashboardState()

        with (
            patch(
                'counter_cruiser.client.__main__._configure_logging'
            ) as configure_logging,
            patch(
                'counter_cruiser.client.__main__.load_client_config',
                return_value=config,
            ) as load_cfg,
            patch(
                'counter_cruiser.client.__main__.resolve_client_config_path',
                return_value=config_path,
            ),
            patch(
                'counter_cruiser.client.__main__.DashboardState',
                return_value=real_state,
            ),
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
            # ClientSession is wired to the real DashboardState's connection
            # callback, so a transport-level drop updates server_connected.
            assert kwargs['on_connection_change'] == real_state.set_server_connected

            assert signal_signal.call_count == 2
            run.assert_called_once_with(session_instance.run.return_value)

        # Exercise the on_result closure: single frame (debounce not met) —
        # no alert dispatch, but the zone-analysis/log branch is covered.
        box = BoundingBox(
            x1=0, y1=0, x2=10, y2=400, confidence=0.9, class_id=16, class_name='dog'
        )
        msg = DetectionMessage(frame_id=1, boxes=[box], processing_time_ms=2.0)
        on_result(msg, 0.123)
        assert real_state.get_alerts() == []  # debounce not yet met, no alert

        # Second consecutive elevated frame: debounce satisfied, exercising
        # the alert-dispatch branch (AlertContext build + maybe_alert call)
        # and the DashboardState.record_alert wiring.
        msg2 = DetectionMessage(frame_id=2, boxes=[box], processing_time_ms=2.0)
        on_result(msg2, 0.123)
        session_instance.get_frame.assert_called_with(2)

        alerts = real_state.get_alerts()
        assert len(alerts) == 1
        assert alerts[0].frame_id == 2
        assert alerts[0].triggered_zones == frozenset({'counter'})

    def test_main_constructs_dashboard_state_and_starts_web_thread(
        self, monkeypatch, tmp_path
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

        config = ClientSettings(
            alerts=AlertConfig(
                deterrent=DeterrentConfig(stats_db_path=str(tmp_path / 'stats.db'))
            )
        )

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
    def test_all_handlers_disabled_by_default(self, tmp_path) -> None:
        from counter_cruiser.client.__main__ import _build_alert_manager
        from counter_cruiser.client.deterrent_stats import DeterrentStatsStore

        stats_store = DeterrentStatsStore(tmp_path / 'stats.db')
        manager, deterrent = _build_alert_manager(ClientSettings(), stats_store)
        # No handlers/deterrent constructed when everything is disabled.
        assert manager._handlers == []
        assert manager._deterrent is None
        assert deterrent is None

    def test_enabled_handlers_are_constructed(self, tmp_path) -> None:
        from counter_cruiser.client.__main__ import _build_alert_manager
        from counter_cruiser.client.deterrent_stats import DeterrentStatsStore
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
        stats_store = DeterrentStatsStore(tmp_path / 'stats.db')
        manager, deterrent = _build_alert_manager(config, stats_store)
        assert len(manager._handlers) == 3
        assert deterrent is None


class TestBuildAlertManagerWithDeterrent:
    def test_deterrent_enabled_constructs_handler_with_stats_store(
        self, tmp_path
    ) -> None:
        from counter_cruiser.client.__main__ import _build_alert_manager
        from counter_cruiser.client.deterrent_stats import DeterrentStatsStore
        from counter_cruiser.config.models import AlertConfig, DeterrentConfig

        config = ClientSettings(
            alerts=AlertConfig(deterrent=DeterrentConfig(enabled=True, pin=17))
        )
        stats_store = DeterrentStatsStore(tmp_path / 'stats.db')
        with patch(
            'counter_cruiser.client.alerts.deterrent._import_gpio', return_value=None
        ):
            manager, deterrent = _build_alert_manager(config, stats_store)
        assert manager._deterrent is not None
        assert deterrent is not None
        assert deterrent.is_operational is False  # _import_gpio patched to None above


class TestMainCallsAlertManagerCleanupOnShutdown:
    def test_cleanup_called_after_run(self, tmp_path) -> None:
        config = ClientSettings(
            alerts=AlertConfig(
                deterrent=DeterrentConfig(stats_db_path=str(tmp_path / 'stats.db'))
            )
        )
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
            build_manager.return_value = (manager_instance, None)

            main()

            manager_instance.cleanup.assert_called_once_with()


def _free_port() -> int:
    """Return a currently-unused TCP port (best-effort; small race window)."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(('127.0.0.1', 0))
        return sock.getsockname()[1]


class TestWebServerThreading:
    """Regression test for the single-threaded werkzeug server finding.

    Boots the *real* server via `_run_web_server` (not `test_client()`) on
    an ephemeral port, in a background thread, exactly as `main()` does.
    While a `/video_feed` MJPEG stream connection is held open, `/api/status`
    must still respond promptly — proving `threaded=True` is in effect and
    the stream isn't monopolizing the server's sole worker.
    """

    def test_video_feed_does_not_block_api_status(self, tmp_path) -> None:
        host = '127.0.0.1'
        port = _free_port()

        config = ClientSettings(web_host=host, web_port=port, web_stream_fps=5.0)
        config_path = tmp_path / 'client.toml'
        config_path.write_text('')
        state = DashboardState()
        zone_store = ZoneStore(config, config_path)
        app = create_app(state, config, zone_store, FakeStatsStore())

        server_thread = threading.Thread(
            target=_run_web_server, args=(app, host, port), daemon=True
        )
        server_thread.start()

        base_url = f'http://{host}:{port}'
        deadline = time.monotonic() + 5.0
        while time.monotonic() < deadline:
            try:
                requests.get(f'{base_url}/api/status', timeout=0.5)
                break
            except requests.exceptions.ConnectionError:
                time.sleep(0.05)

        # Hold a streaming /video_feed connection open on a background
        # thread; the generator has no max_frames bound (production
        # behaviour), so it keeps emitting until this thread closes it.
        stop_streaming = threading.Event()

        def hold_stream() -> None:
            with requests.get(
                f'{base_url}/video_feed', stream=True, timeout=10
            ) as resp:
                for _ in resp.iter_content(chunk_size=1024):
                    if stop_streaming.is_set():
                        break

        stream_thread = threading.Thread(target=hold_stream, daemon=True)
        stream_thread.start()
        time.sleep(0.2)  # let the stream connection establish and start emitting

        try:
            start = time.monotonic()
            status_response = requests.get(f'{base_url}/api/status', timeout=2.0)
            elapsed = time.monotonic() - start
        finally:
            stop_streaming.set()
            stream_thread.join(timeout=2.0)

        assert status_response.status_code == 200
        assert status_response.json()['server_connected'] is False
        # A single-threaded server would have queued this behind the
        # still-open /video_feed connection; a threaded one answers almost
        # immediately.
        assert elapsed < 1.0


class TestDeterrentStatsWiring:
    def test_deterrent_configured_and_operational_pushes_status(self, tmp_path) -> None:
        from counter_cruiser.config.models import AlertConfig, DeterrentConfig

        db_path = tmp_path / 'stats.db'
        config = ClientSettings(
            alerts=AlertConfig(
                deterrent=DeterrentConfig(
                    enabled=True, pin=17, stats_db_path=str(db_path)
                )
            )
        )
        real_state = DashboardState()

        with (
            patch('counter_cruiser.client.__main__._configure_logging'),
            patch(
                'counter_cruiser.client.__main__.load_client_config',
                return_value=config,
            ),
            patch(
                'counter_cruiser.client.__main__.DashboardState',
                return_value=real_state,
            ),
            patch('counter_cruiser.client.__main__.OpenCVCapture'),
            patch('counter_cruiser.client.__main__.ClientSession') as session_cls,
            patch('counter_cruiser.client.__main__.signal.signal'),
            patch('counter_cruiser.client.__main__.asyncio.run'),
            patch('counter_cruiser.client.__main__.threading.Thread') as thread_cls,
            patch(
                'counter_cruiser.client.alerts.deterrent._import_gpio',
                return_value=None,  # forces is_operational=False deterministically
            ),
        ):
            thread_cls.return_value = MagicMock()
            session_cls.return_value.frame_height = config.frame_height

            main()

        status = real_state.get_deterrent_status()
        assert status.configured is True
        assert status.operational is False  # _import_gpio returns None above

    def test_deterrent_disabled_pushes_not_configured_status(self, tmp_path) -> None:
        config = ClientSettings(
            alerts=AlertConfig(
                deterrent=DeterrentConfig(stats_db_path=str(tmp_path / 'stats.db'))
            )
        )  # deterrent disabled by default
        real_state = DashboardState()

        with (
            patch('counter_cruiser.client.__main__._configure_logging'),
            patch(
                'counter_cruiser.client.__main__.load_client_config',
                return_value=config,
            ),
            patch(
                'counter_cruiser.client.__main__.DashboardState',
                return_value=real_state,
            ),
            patch('counter_cruiser.client.__main__.OpenCVCapture'),
            patch('counter_cruiser.client.__main__.ClientSession') as session_cls,
            patch('counter_cruiser.client.__main__.signal.signal'),
            patch('counter_cruiser.client.__main__.asyncio.run'),
            patch('counter_cruiser.client.__main__.threading.Thread') as thread_cls,
        ):
            thread_cls.return_value = MagicMock()
            session_cls.return_value.frame_height = config.frame_height

            main()

        status = real_state.get_deterrent_status()
        assert status.configured is False
        assert status.operational is False
