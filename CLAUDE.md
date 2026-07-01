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
  helper — boxes, zone polygons, timestamp — reused by the alert system
  and the web UI), `alerts/` (`AlertManager` — per-zone cooldown,
  deterrent-first isolated fan-out; `DeterrentHandler` — GPIO
  button-press simulation on the existing ultrasonic trainer;
  `SnapshotHandler`, `LogHandler`, `NotificationHandler` — recording and
  ntfy.sh/Pushover push notifications), `__main__.py` (entrypoint wiring
  config, camera, transport, zone analysis, debounce, and alert
  dispatch)
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

# Run client
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
