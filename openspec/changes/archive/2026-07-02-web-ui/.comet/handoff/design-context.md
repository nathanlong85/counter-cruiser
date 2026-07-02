# Comet Design Handoff

- Change: web-ui
- Phase: design
- Mode: compact
- Context hash: 6b16f72fab184781e7313280e8f27f50b6a92b8a7e2f5a11faf25a5df6db0aeb

Generated-by: comet-handoff.sh

OpenSpec remains the canonical capability spec. This handoff is a deterministic, source-traceable context pack, not an agent-authored summary.

## openspec/changes/web-ui/proposal.md

- Source: openspec/changes/web-ui/proposal.md
- Lines: 1-76
- SHA256: 9f8674b140a354b29560d6099e905470bbd30d3bba86276471dafb9622b40054

```md
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
```

## openspec/changes/web-ui/design.md

- Source: openspec/changes/web-ui/design.md
- Lines: 1-215
- SHA256: 8198cb84d7b357bf7445d0bafec20a26e701b82e742e7a103201adf16d44aaaa

[TRUNCATED]

```md
## Context

The foundation change delivers the end-to-end detection pipeline (Pi captures →
server infers → Pi runs zone analysis → console reports floor/elevated) plus
typed, file-based configuration with TOML-defined zones. The pipeline currently
has no human-facing surface: you cannot see the camera, judge latency, confirm
detection, or edit zones without an attached monitor and the old OpenCV-window
calibration tool.

This change adds a browser-based UI **served from the Pi/client**, which owns the
camera and the zones. The Pi 3B is the binding constraint: 1 GB RAM and a weak
CPU. The UI is a VIEW plus a zone-config editor over the running client; it does
no inference. It reads the current annotated frame and stats from the client and
writes zone edits back to the TOML config.

The `no-diggity` POC had a working Flask + SocketIO dashboard, but it was built on
module-level mutable globals guarded by a `Lock`, duplicated the OpenCV drawing
code across `web_server.py`, `calibrate_zones.py`, and `main.py`, and used
`print()` throughout — all of which make the 100% coverage goal unreachable. This
design deliberately reverses those patterns.

## Goals / Non-Goals

**Goals:**
- A lightweight Flask web server co-located with the client on the Pi 3B.
- A live MJPEG feed of the annotated frame (boxes colored by elevated state, zone
  polygons, status/FPS overlay), bounded in frame rate, graceful before first
  frame.
- Web-based zone calibration (view/create/edit/delete/enable) over the live frame,
  validated like the file config (polygon ≥ 3 points), persisted back to the
  client TOML so the file stays the source of truth.
- A status dashboard + JSON status endpoint: detection state, FPS, latency,
  server-connection status, recent alerts.
- An encapsulated, injected UI state object replacing the POC's globals, making
  the whole server testable with Flask's test client and injected fakes (100%
  coverage).
- One shared frame-annotation component, reusable by the alert-system snapshot
  handler.

**Non-Goals:**
- Performing detection or zone analysis in the web layer (that is the pipeline's
  job; the UI only reads results).
- Authentication / TLS (trusted home LAN, consistent with the foundation).
- Recording, multi-camera, historical analytics, or a snapshot gallery beyond the
  bounded in-memory alert history (snapshots are an alert-system concern).
- The alert-system itself (GPIO, snapshot files, push) — this change only reads
  alert events for display and shares the annotation code.

## Decisions

### Flask with a streaming response for MJPEG

Keep Flask (carried from the POC) but structure it cleanly behind an application
factory (`create_app(state, settings) -> Flask`). The live feed is a standard
Flask streaming `Response` with mimetype `multipart/x-mixed-replace; boundary=frame`,
yielding JPEG-encoded annotated frames from a generator.

**Why:** Flask is already proven for this exact job, is light enough for the Pi,
and the app-factory pattern lets tests build an app around injected fakes. The
MJPEG-over-streaming-Response approach worked in the POC and needs no client-side
library — an `<img src="/video_feed">` tag just works on a phone.

**Alternative considered:** a heavier ASGI stack (FastAPI/Starlette + uvicorn).
Rejected — no async benefit here that justifies the extra footprint on a Pi 3B,
and the client pipeline's asyncio loop is separate from the (threaded) web server.

### Encapsulated, injected UI state — not module globals

Introduce a `DashboardState` (or `UiState`) object that owns: the latest captured
frame, current detections, current stats (FPS, latency, server status), current
detection/zone result, and a bounded deque of recent alerts. It exposes
thread-safe update methods (called by the client) and read methods (called by the
endpoints). It is constructed once at entrypoint and **injected** into
`create_app`; route handlers close over it (or read it from the app context). The
module defines no mutable globals.

**Why:** the POC's `dashboard_state` dict + `state_lock` at module scope made the
server impossible to test in isolation and impossible to run two instances of. An
injected object is trivially replaced with a fake in tests and is the single hard
requirement driving the 100% coverage goal. A lock (or a thread-safe structure)
```

Full source: openspec/changes/web-ui/design.md

## openspec/changes/web-ui/tasks.md

- Source: openspec/changes/web-ui/tasks.md
- Lines: 1-59
- SHA256: 727093e95d67a53f1ef9d8fe3dc01ee2d1d8d0dc2a84d12bc0f9f8f118ba1e8a

```md
## 1. Scaffolding & dependencies

- [ ] 1.1 Add `flask` to the client dependencies in `pyproject.toml` (keep `flask-socketio` out unless polling is later rejected)
- [ ] 1.2 Create the `client/web/` subpackage (app factory, state, routes, zone writer, templates) and matching `tests/client/web/` tree (frame annotation is owned by the alert-system change at `client/annotation.py` and is imported, not recreated here)
- [ ] 1.3 Confirm pytest/coverage config covers the new package (`--cov-fail-under=100`, carried-over `exclude_lines`); no `print()`, logging facade only

## 2. Frame annotation (consumed from alert-system)

- [ ] 2.1 Confirm the shared `annotate_frame(frame, detections, zones, status)` component from `client/annotation.py` (implemented in the alert-system change) exposes what the live feed needs; if alert-system has not yet landed it, that is a sequencing prerequisite for this change
- [ ] 2.2 Write a test that the live feed calls the shared annotation component (asserts it is invoked with the current frame/detections/zones/status) rather than re-drawing — no second copy of the drawing logic in `client/web/`

## 3. Encapsulated UI state object

- [ ] 3.1 Write tests: update methods set frame/detections/stats/result; read methods return them; recent-alert history is bounded and newest-first; thread-safe copy-on-read of frame; "no frame yet" returns the no-frame sentinel
- [ ] 3.2 Implement the injected `DashboardState` object (internal lock, bounded alert deque, frame/stats/result holders); no module-level mutable state

## 4. App factory & test harness

- [ ] 4.1 Write tests: `create_app(state, settings)` builds an app exercisable via `test_client()` with a fake state and no real camera/socket
- [ ] 4.2 Implement `create_app(state, settings)` wiring the injected state into route handlers (app factory, no import-time side effects)

## 5. Status dashboard (status-dashboard)

- [ ] 5.1 Write tests for the status JSON endpoint: returns detection state/triggered zones/FPS/latency/server status; elevated vs floor reflected; disconnected server reflected
- [ ] 5.2 Implement the status JSON endpoint reading from the injected state
- [ ] 5.3 Write tests for the alert-history endpoint: newest-first, bounded, empty-when-none
- [ ] 5.4 Implement the alert-history endpoint reading the bounded deque
- [ ] 5.5 Write a test that the dashboard HTML page is served
- [ ] 5.6 Implement the dashboard page template (status + stats + recent alerts + embedded live feed) polling the JSON endpoints on an interval

## 6. Live feed (live-feed)

- [ ] 6.1 Write tests (consume a bounded number of MJPEG parts via an injected clock/limit): stream yields JPEG annotated frames; detection box color follows elevated state; zones + overlay present
- [ ] 6.2 Write tests for the no-frame-yet case: placeholder served, response stays open until a real frame arrives
- [ ] 6.3 Write a test that the emission rate is bounded by the configured maximum
- [ ] 6.4 Implement the MJPEG generator (calls the shared annotation component, bounded rate, placeholder before first frame) and the `multipart/x-mixed-replace` streaming Response endpoint

## 7. Zone calibration (zone-calibration)

- [ ] 7.1 Write tests for the get-zones endpoint: returns id/name/enabled/polygon per zone; empty set when none configured
- [ ] 7.2 Implement the get-zones endpoint reading current config zones
- [ ] 7.3 Write tests for create/edit/toggle/delete: valid create, polygon edit, enabled toggle, delete; polygon < 3 points rejected; edit/delete of non-existent zone returns not-found
- [ ] 7.4 Implement create/edit/toggle/delete handlers validating via the foundation `Zone` model
- [ ] 7.5 Write tests for TOML write-back (temp config file): valid edit persists and reloads identically; rejected edit leaves file unchanged; write is atomic
- [ ] 7.6 Implement the atomic write-back of the zones section to the client TOML config (temp-then-rename), preserving other settings
- [ ] 7.7 Write a test that the calibration page is served with the live frame as backdrop
- [ ] 7.8 Implement the calibration page template (draw/edit polygons over the live frame, calling the zone endpoints)

## 8. Client integration

- [ ] 8.1 Write a test that the client entrypoint constructs the `DashboardState`, builds the app, and starts the web server thread without starting real capture
- [ ] 8.2 Wire the client pipeline to push latest frame/detections/stats/result/alerts into the injected `DashboardState`, and start the Flask server (bounded, single-process) alongside the capture loop

## 9. Finalization

- [ ] 9.1 Run the full test suite; confirm 100% coverage on the web package
- [ ] 9.2 Run `ruff check` and `ruff format`; resolve all findings
- [ ] 9.3 Verify docstrings on all public modules/classes/functions in `client/web/`
- [ ] 9.4 Update root `CLAUDE.md` Commands/Architecture sections with how to run the web UI
```

## openspec/changes/web-ui/specs/live-feed/spec.md

- Source: openspec/changes/web-ui/specs/live-feed/spec.md
- Lines: 1-58
- SHA256: eacc627e746dbf0477cf3d2ea12cb7ff9992e3b4d7b9dd173a08a23faf92d681

```md
## ADDED Requirements

### Requirement: Annotated MJPEG live feed

The web server SHALL expose an HTTP endpoint that streams the current camera
frame as a multipart MJPEG response. Each streamed frame SHALL be the annotated
frame — the captured image with detection bounding boxes, enabled zone polygons,
and a status/FPS overlay drawn on it — so a browser can confirm camera aim and
observe detection in real time.

#### Scenario: Stream serves annotated frames

- **WHEN** a browser requests the live-feed endpoint while frames are being captured
- **THEN** the server returns a multipart `multipart/x-mixed-replace` response whose parts are JPEG-encoded annotated frames

#### Scenario: Detection box reflects elevated state by color

- **WHEN** the current frame's detection is classified as elevated versus on the floor
- **THEN** the detection bounding box is drawn red for elevated and green for not-elevated

#### Scenario: Zones and status overlay are drawn

- **WHEN** a frame is annotated for the stream
- **THEN** enabled zone polygons and a status/FPS overlay are drawn on the frame in addition to any detection boxes

### Requirement: Graceful handling of no available frame

The live feed SHALL handle the case where no camera frame has been captured yet
(e.g. at startup) without erroring or closing the connection. It SHALL serve a
placeholder until a real frame is available.

#### Scenario: No frame captured yet

- **WHEN** the live-feed endpoint is requested before any frame has been captured
- **THEN** the server serves a placeholder frame and the response remains open, beginning to serve real frames once capture produces one

### Requirement: Bounded stream frame rate

The live feed SHALL limit the rate at which frames are emitted to a bounded
maximum to protect the Raspberry Pi 3B's limited CPU, rather than emitting frames
as fast as possible.

#### Scenario: Emission rate is capped

- **WHEN** annotated frames are available faster than the configured maximum stream rate
- **THEN** the stream emits frames no faster than the bounded maximum rate

### Requirement: Shared frame-annotation logic

The live feed SHALL produce its annotated frames using the single shared
frame-annotation component (`client/annotation.py`, owned by the alert-system
capability), rather than carrying its own copy of the box/zone/overlay drawing
logic.

#### Scenario: Annotation produced by the shared component

- **WHEN** the live feed annotates a frame for streaming
- **THEN** it produces the annotated image via the shared annotation component given the frame, detections, zones, and status, without its own copy of the drawing logic
```

## openspec/changes/web-ui/specs/status-dashboard/spec.md

- Source: openspec/changes/web-ui/specs/status-dashboard/spec.md
- Lines: 1-83
- SHA256: ee3000c55177e3ecb61cb4c9d7457d88f36c5f99a5b1cddf9cbe6e8c432d43d1

[TRUNCATED]

```md
## ADDED Requirements

### Requirement: Status JSON endpoint

The web server SHALL expose a JSON endpoint returning the current operational
status: detection state (floor or elevated and which zones are triggered), camera
FPS, round-trip latency, and server-connection status.

#### Scenario: Status is returned as JSON

- **WHEN** a client requests the status endpoint
- **THEN** the server returns a JSON object containing detection state, triggered zones, camera FPS, round-trip latency, and server-connection status

#### Scenario: Elevated detection state is reflected

- **WHEN** the latest analyzed frame is classified as elevated within one or more zones
- **THEN** the status reports the detection state as elevated together with the triggered zone identifiers

#### Scenario: Floor detection state is reflected

- **WHEN** the latest analyzed frame is not classified as elevated
- **THEN** the status reports the detection state as floor with no triggered zones

#### Scenario: Disconnected server is reflected

- **WHEN** the client's connection to the inference server is down
- **THEN** the status reports the server-connection status as disconnected

### Requirement: Recent alert history

The web server SHALL expose a recent alert history. The history SHALL be bounded
to a maximum number of entries, discarding the oldest when the limit is exceeded,
and each entry SHALL record its time, the triggered zones, and the originating
frame identifier.

#### Scenario: Recent alerts are returned newest-first

- **WHEN** a client requests the alert history
- **THEN** the server returns the recent alerts ordered most-recent first, each with its time, triggered zones, and frame identifier

#### Scenario: History is bounded

- **WHEN** more alerts are recorded than the configured maximum history size
- **THEN** the oldest alerts are discarded so the history never exceeds the maximum

#### Scenario: No alerts yet

- **WHEN** no alerts have been recorded
- **THEN** the server returns an empty alert history without erroring

### Requirement: Dashboard page

The web server SHALL serve an HTML dashboard page that presents the status, stats,
and recent alert history together with the live feed for at-a-glance monitoring
from a phone or laptop.

#### Scenario: Dashboard page is served

- **WHEN** a browser requests the dashboard page
- **THEN** the server returns an HTML page presenting status, stats, recent alerts, and the live feed

### Requirement: Encapsulated, injected UI state

The web server's view of status, stats, frame, and alert history SHALL be held in
an encapsulated state/service object that is injected into the application rather
than stored in module-level globals. The running client SHALL update this object
with the latest frame, stats, and detection results, and the web endpoints SHALL
read from it.

#### Scenario: Client updates and endpoints read the same injected state

- **WHEN** the client pushes a new frame, stats, and detection result into the injected UI state object
- **THEN** subsequent requests to the status, alert, and live-feed endpoints reflect those updated values

#### Scenario: Server is testable with injected fake state

- **WHEN** the web server is constructed in a test with a fake UI state object and no real camera or socket
- **THEN** all endpoints can be exercised through the test client using only the injected state

#### Scenario: No module-level mutable state
```

Full source: openspec/changes/web-ui/specs/status-dashboard/spec.md

## openspec/changes/web-ui/specs/zone-calibration/spec.md

- Source: openspec/changes/web-ui/specs/zone-calibration/spec.md
- Lines: 1-106
- SHA256: 39005adb4a0654e7939caedbe264564b3dbac99418a2cd5df438de953c8fdda3

[TRUNCATED]

```md
## ADDED Requirements

### Requirement: View current zones

The web server SHALL expose the current zone definitions (identifier, display
name, enabled flag, and polygon points) plus a config version token, so the
calibration UI can render them over the live frame for editing and submit
that version with subsequent edit requests.

#### Scenario: Current zones are returned

- **WHEN** the calibration UI requests the current zones
- **THEN** the server returns each configured zone with its identifier, display name, enabled flag, and polygon points, together with a version token identifying the current state of the config file

#### Scenario: No zones configured

- **WHEN** the configuration defines no zones
- **THEN** the server returns an empty set of zones without erroring

### Requirement: Create and edit zones

The web server SHALL accept requests to create a new zone or edit an existing
zone's polygon, display name, or enabled flag. A created or edited polygon SHALL
be validated to contain at least three points, consistent with the foundation
`configuration` capability.

#### Scenario: Create a valid zone

- **WHEN** a request creates a zone with a name and a polygon of three or more points
- **THEN** the server adds the zone and reports success

#### Scenario: Edit an existing zone's polygon

- **WHEN** a request updates an existing zone's polygon to a new set of three or more points
- **THEN** the server replaces that zone's polygon with the new points

#### Scenario: Toggle a zone's enabled flag

- **WHEN** a request changes an existing zone's enabled flag
- **THEN** the server updates the zone's enabled state without altering its polygon

#### Scenario: Polygon with fewer than three points is rejected

- **WHEN** a create or edit request supplies a polygon with fewer than three points
- **THEN** the server rejects the request with a validation error and does not modify any zone

#### Scenario: Edit of a non-existent zone is rejected

- **WHEN** a request edits or deletes a zone identifier that does not exist
- **THEN** the server rejects the request with a not-found error and makes no change

### Requirement: Conflicting edit is rejected

The web server SHALL reject a create, edit, delete, or toggle request whose
submitted version token does not match the config file's current version,
without modifying the config file. This detects the config file having
changed (by a hand-edit or another web request) since the client last read
the zone set.

#### Scenario: Stale version is rejected

- **WHEN** a create, edit, delete, or toggle request submits a version token that does not match the config file's current version
- **THEN** the server rejects the request with a conflict error and does not modify the config file

### Requirement: Delete zones

The web server SHALL accept requests to delete an existing zone by its
identifier.

#### Scenario: Delete an existing zone

- **WHEN** a request deletes an existing zone by identifier
- **THEN** the server removes that zone and reports success

### Requirement: Persist zone edits to the client TOML config

The server SHALL persist the resulting zone set back to the client TOML
configuration file whenever a zone is created, edited, deleted, or toggled through
the web UI, so that the file remains the single source of truth and the change
survives a restart. Persistence SHALL only occur after validation succeeds.
```

Full source: openspec/changes/web-ui/specs/zone-calibration/spec.md

