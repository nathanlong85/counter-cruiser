# CLAUDE.md

<!-- Load the main, committed ruleset from AGENTS.md -->
@AGENTS.md

## Architecture

Single `counter_cruiser` package managed with `uv`. Sub-packages:

- `shared/`: `geometry.py` (point-in-polygon containment + elevated-position decision and zone aggregation), `debounce.py` (`DetectionHistory`, consecutive-elevated-frame debouncing), `protocol.py` (Pydantic message models — `FrameMessage`, `DetectionMessage`, `ErrorMessage`, `PingMessage`, `PongMessage` — plus frame encode/decode and JSON serialize/deserialize)
- `config/`: `models.py` (`Zone`, `ClientSettings`, `ServerSettings` pydantic-settings models), `loader.py` (TOML file + env-var loading, env overrides file)
- `client/`: `capture.py` (`CameraCapture` protocol + `OpenCVCapture`
  implementation), `transport.py` (`ClientSession` — connects to the
  server, sends frames, matches detections, retains a bounded frame ring
  buffer, handles reconnect), `annotation.py` (shared `annotate_frame`
  helper — boxes, zone polygons, timestamp, box color by elevated state —
  reused by the alert system and the web UI), `alerts/` (`AlertManager` —
  per-zone cooldown, deterrent-first isolated fan-out; `DeterrentHandler` —
  GPIO button-press simulation on the existing ultrasonic trainer, exposing an `is_operational` status and recording each attempt's outcome via the injected `DeterrentStatsStore`;
  `SnapshotHandler`, `LogHandler`, `NotificationHandler` — recording and
  ntfy.sh/Pushover push notifications), `web/` (`DashboardState` — injected,
  thread-safe UI state, including deterrent operational status;
  `create_app` — Flask app factory; `mjpeg.py` —
  rate-limited MJPEG generator; `zone_store.py` — `ZoneStore`, zone CRUD
  with mtime-based optimistic concurrency and atomic TOML write-back;
  `routes_dashboard.py`/`routes_live_feed.py`/`routes_zones.py`/
  `routes_deterrent_stats.py` — route registration; `templates/` —
  dashboard, calibration, and training-progress pages), `deterrent_stats.py`
  (`DeterrentStatsStore` — SQLite-backed persistent recorder for deterrent
  trigger attempts, one fresh connection per access, WAL mode), `__main__.py`
  (entrypoint wiring config, camera, transport, zone analysis, alert
  dispatch, and the web server thread)
- `server/`: `model.py` (`DetectionModel` ABC, `YOLOAdapter`, `select_device` auto device selection), `handler.py` (`handle_connection` — per-connection WebSocket message dispatch), `__main__.py` (entrypoint)

Zone analysis and debouncing live on the client. The server is a stateless inference service: it decodes frames, runs detection, and replies with `DetectionMessage`/`ErrorMessage`/`PongMessage` — it has no notion of zones or elevated status.

## Commands

```bash
# Install (editable, with dev extras)
uv pip install -e ".[dev]"

# Run tests with coverage (line + branch, 100% required)
pytest

# Lint
ruff check .

# Format
ruff format .

# Run server (requires server extra: torch + ultralytics)
uv pip install -e ".[server]"
python -m counter_cruiser.server

# Run client (also starts the web UI on http://<web_host>:<web_port>/, default
# 0.0.0.0:8080; includes /training-progress for deterrent usage history)
python -m counter_cruiser.client
```

<!-- Command registry — reinforced here so it survives deep-task focus drift -->
> **MANDATORY — Command Registry:** Check `creg search` BEFORE every shell command.
> After any new command succeeds, run `creg add` IMMEDIATELY — before your next action.
> Print one line: `Command registry: added <id>` or `Command registry: updated <id>`.
> Anti-pattern entries are as important as templates — record failures too.

<!-- Load the local, uncommitted Claude rules -->
<!--Local Claude separated rules-->
**Always check and follow all rules in `.claude/rules/local/`** at session start, even though that directory is gitignored.

<!--Local CLAUDE.* monolith rules-->
@CLAUDE.local.md
@.claude/CLAUDE.local.md
