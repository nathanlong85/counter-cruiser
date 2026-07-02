# counter-cruiser

An attempt to discourage dogs from stealing food off the kitchen counter.

A Raspberry Pi watches the counter with a camera, sends frames to an
inference server for dog detection, decides whether the dog is "elevated"
(paws on the counter) within one or more defined zones, and — after a few
consecutive elevated frames — fires a deterrent and records/notifies. A
browser-based dashboard lets you watch the live feed, check status, and draw
zones without an attached monitor.

## Architecture

Two processes talk over a WebSocket:

- **Client** (`counter_cruiser.client`, runs on the Pi): owns the camera,
  captures frames, sends them to the server, receives detections back,
  decides floor-vs-elevated per zone, debounces (requires several
  consecutive elevated frames before acting), and dispatches alerts. Also
  runs a small Flask web server on a background thread — a live annotated
  MJPEG feed, a status/alerts dashboard, and a browser-based zone editor
  that persists changes back to the client's TOML config.
- **Server** (`counter_cruiser.server`): a stateless inference service. It
  decodes incoming frames, runs a YOLO object-detection model, and replies
  with the detected bounding boxes. It has no notion of zones, elevated
  state, or alerts — all of that logic lives on the client.

```
┌─────────────────────────┐  frames   ┌──────────────────────┐
│  client (Raspberry Pi)  │ ────────► │  server (GPU/CPU box)│
│  camera → zone analysis │ ◄──────── │  YOLO detection       │
│  → debounce → alerts    │ detections└──────────────────────┘
│  → web UI (Flask)       │
└─────────────────────────┘
        ▲
        │ browser (LAN)
```

See [`CLAUDE.md`](CLAUDE.md) for the full package-by-package breakdown of
`counter_cruiser/{shared,config,client,server}`.

## Requirements

- Python 3.11+
- [`uv`](https://docs.astral.sh/uv/) for dependency management
- A camera the client process can open (e.g. USB webcam or the Pi camera via
  a V4L2-compatible interface)
- For the server: a machine that can run PyTorch/Ultralytics (GPU optional
  but recommended — the client is intended for a Raspberry Pi 3B, which is
  not powerful enough to run inference itself)
- Optional: a GPIO-connected deterrent (e.g. an ultrasonic trainer wired to
  a Pi GPIO pin) for the `deterrent` alert handler

## Installation

```bash
# Client-only install (editable, with dev extras for testing)
uv pip install -e ".[dev]"

# Server install adds the inference stack (torch + ultralytics)
uv pip install -e ".[server]"

# On a Raspberry Pi, add GPIO support for the deterrent handler
uv pip install -e ".[gpio]"
```

## Configuration

Both the client and server load typed configuration from TOML files (see
[`fixtures/client.toml`](fixtures/client.toml) and
[`fixtures/server.toml`](fixtures/server.toml) for annotated examples).

```bash
mkdir -p config
cp fixtures/client.toml config/client.toml
cp fixtures/server.toml config/server.toml
```

Edit `config/client.toml` for your setup — camera index, the server's
address, zone polygons, and which alert handlers are enabled. Edit
`config/server.toml` for the inference server's host/port and detection
model. Config file location can be overridden with the
`COUNTER_CRUISER_CONFIG` environment variable, and any setting can be
overridden with a `COUNTER_CRUISER_<SETTING>` environment variable
(pydantic-settings), which always takes priority over the file.

Zones are polygons (three or more `[x, y]` points) with an id, display name,
and enabled flag:

```toml
[[counter_cruiser.zones]]
id = "counter"
name = "Kitchen Counter"
enabled = true
polygon = [[100, 80], [540, 80], [540, 360], [100, 360]]
```

Zones can also be created, edited, and deleted from the browser-based
calibration page (see below) — edits are written back to the TOML file, so
the file remains the single source of truth either way.

## Running

Start the inference server first (on a machine with the `server` extra
installed):

```bash
python -m counter_cruiser.server
```

Then start the client (on the Raspberry Pi, or any machine with a camera):

```bash
python -m counter_cruiser.client
```

The client starts the capture pipeline and, on the same process, a web
server — by default at `http://0.0.0.0:8080/` (configurable via
`web_host`/`web_port` in `config/client.toml`). Open that address from a
phone or laptop on the same LAN to see:

- **`/`** — the dashboard: current detection state (floor/elevated +
  triggered zones), camera FPS, round-trip latency, server-connection
  status, recent alert history, and the embedded live feed.
- **`/video_feed`** — the raw MJPEG stream (annotated: detection boxes
  colored red when elevated / green when not, zone polygons, status
  overlay), bounded to a low frame rate to keep the Pi's CPU usage down.
- **`/calibrate`** — draw, edit, enable/disable, and delete zones over the
  live feed. Edits persist to `config/client.toml` immediately.

The web UI is trusted-LAN-only — there is no authentication or TLS.

## Alerts

When the debounced elevated state triggers (at least two elevated frames
within a small frame-id window, tolerating gaps — filters out single-frame
detection noise), the client fans out to whichever alert
handlers are enabled in `config/client.toml`, all under a shared per-zone
cooldown:

| Handler | What it does |
|---|---|
| `deterrent` | Simulates a button press on a GPIO-connected device (e.g. an ultrasonic trainer) |
| `snapshot` | Saves an annotated image of the triggering frame to disk (bounded count) |
| `log` | Appends a structured line to a local alert log file |
| `notification` | Sends a push notification via ntfy.sh or Pushover |

The deterrent (if enabled) fires first and in isolation from the other
handlers, so a slow notification API can't delay the physical response.

## Development

```bash
# Run the full test suite (100% line + branch coverage required)
pytest

# Lint
ruff check .

# Format
ruff format .
```

Tests are organized to mirror the package layout (`tests/client/`,
`tests/server/`, `tests/shared/`, `tests/config/`), with integration-style
tests at `tests/test_integration.py`. All tests run against injected fakes —
no real camera, socket, or GPIO hardware is required to run the suite.
