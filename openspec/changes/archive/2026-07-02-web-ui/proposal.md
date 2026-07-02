## Why

The running client on the Raspberry Pi is currently a black box: there is no way
to confirm where the camera is pointed, see whether detection is working, judge
end-to-end latency, or define counter zones without an attached monitor and the
OpenCV-window calibration tool. The user needs a browser-based view (phone or
laptop) that shows the live annotated feed, lets them draw and edit zones from
anywhere on the LAN, and surfaces detection state and stats — all running
lightweight on the Pi 3B itself, which owns the camera and the zone config.

## What Changes

- Add a Flask-based web server that runs **on the Pi/client** alongside the
  capture pipeline, exposing a small set of pages and JSON/streaming endpoints.
- Serve a **live MJPEG feed** of the annotated current frame (detection box
  green/red by elevated state, zone polygons, FPS/status overlay), bounded to a
  low frame rate to protect the Pi, and degrading gracefully when no frame has
  been captured yet.
- Provide **web-based zone calibration**: view current zones over the live frame,
  create/edit/delete polygons, toggle enabled state, with the same validation as
  the file-based config (polygon ≥ 3 points). Edits are **persisted back to the
  client TOML config** so the file remains the single source of truth and changes
  survive restart.
- Provide a **status dashboard**: detection state (floor/elevated + triggered
  zones), camera FPS, round-trip latency, server-connection status, and recent
  alert history, served as a page plus a JSON status endpoint.
- Introduce an **encapsulated, injected UI state/service object** that the running
  client updates with the latest frame/stats — explicitly replacing the POC's
  module-level globals + Lock so the web server is testable with Flask's test
  client and no real camera/socket.
- Establish a **shared frame-annotation concern**: the drawing logic (boxes,
  zones, overlay) is factored so it is not duplicated between the live feed here
  and the alert-system snapshot handler (a later change).

## Capabilities

### New Capabilities
- `live-feed`: MJPEG streaming endpoint serving the annotated current frame
  (detection boxes + zone polygons + status/FPS overlay); handles the "no frame
  yet" case gracefully and bounds the stream frame rate to protect the Pi 3B.
- `zone-calibration`: Web-based zone editing — view, create, edit, delete, and
  enable/disable polygon zones over the live frame, with validation consistent
  with the foundation `configuration` capability, and persistence of edits back
  to the client TOML config (file remains source of truth).
- `status-dashboard`: Status/stats view plus a JSON status API — detection
  state, FPS, latency, server-connection status, and recent alert history, backed
  by an encapsulated (non-global) UI state object updated by the client.

### Modified Capabilities
<!-- None — greenfield. This change reads from the foundation capabilities
     (configuration, detection-pipeline, zone-analysis) and adds new capabilities;
     it does not change their requirements. -->

## Impact

- **Runs on**: the Pi/client. Must stay lightweight (1 GB RAM, weak CPU) —
  bounded MJPEG frame rate; polling-over-SocketIO recommended for stats (see
  design.md).
- **Depends on foundation**: `configuration` (zones + client settings, and the
  TOML write-back path), `detection-pipeline` (current annotated frame + stats:
  FPS, latency, server status, detection state), and `zone-analysis` (the
  elevated/triggered-zone result and the polygon-validation rule).
- **Cross-change shared concern**: frame-annotation drawing logic is shared with
  the alert-system snapshot handler (a later change) — flagged here so the two
  changes converge on one implementation rather than duplicating it as the POC
  did.
- **New code**: a `client/web/` (or equivalent) subpackage — Flask app factory,
  the injected UI state/service, route handlers, MJPEG generator, zone-config
  writer, and templates — plus a matching `tests/` tree.
- **Dependencies**: adds `flask` to the client deps (and optionally
  `flask-socketio` only if real-time push is adopted — default is polling).
- **No detection logic**: the web UI is a VIEW + zone editor over the running
  client; it performs no inference itself.
- **Quality gates** (unchanged, enforced): 100% coverage
  (`--cov-fail-under=100`), no module-level mutable state, dependency injection,
  logging facade (no `print()`), docstrings on public APIs, ruff clean.
