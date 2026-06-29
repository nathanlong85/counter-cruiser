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
is still needed because the client thread writes while request threads read — but
it lives *inside* the object, not at module scope.

**Alternative considered:** Flask `g`/app config only. Rejected — those are
request-scoped or read-mostly; we need a long-lived, mutable, thread-safe holder
that the client updates between requests.

### Polling over SocketIO (recommended)

Recommend **HTTP polling** for stats/status/alerts (the dashboard page polls the
JSON endpoints on an interval) rather than SocketIO push. SocketIO remains an
optional later addition if real-time push proves necessary.

**Why:** on a Pi 3B, SocketIO adds a persistent connection per viewer, an
eventlet/gevent worker model, and a heavier dependency — cost that is hard to
justify for a single-household dashboard refreshing every second or two. Polling a
small JSON endpoint is cheap, simpler to test (plain request/response, no async
socket harness), and avoids the POC's `allow_unsafe_werkzeug` hack. The live feed
is already a continuous MJPEG stream, so the "live" need is covered without
sockets.

**Trade-off:** polling adds latency (up to one poll interval) to stat updates and
some redundant requests. Acceptable for a status panel; revisit only if a genuine
real-time push need appears.

### Write-back to TOML, file remains source of truth

Zone edits made in the UI are validated (same rules as the foundation
`configuration` `Zone` model — polygon ≥ 3 points), applied to the in-memory zone
set, and then **serialized back to the client TOML config file**, rewriting the
`[[zones]]` array-of-tables. Reads in the UI come from the same config the client
loaded. On client restart, the file is reloaded normally, so persisted edits
survive and stay consistent with hand-edits.

**Why:** the user wants zones editable both by hand in TOML and in the browser,
with the file authoritative. Writing back keeps a single source of truth and
avoids a divergent in-memory-only zone set. Reusing the foundation `Zone`
validation guarantees the web path can never persist something the file loader
would reject.

**Reconciliation / trade-off:** the config file is rewritten on save. To avoid
clobbering unrelated content we write only the zones section through the typed
config writer and preserve other settings; comments in the rewritten zones block
may not be perfectly preserved (a known TOML-round-trip limitation). The write
should be atomic (write-temp-then-rename) so a crash mid-save cannot corrupt the
config. Concurrent hand-edit + web-edit is not coordinated — last-writer-wins,
acceptable for a single-user home system; noted as an open question if it bites.

### Shared frame-annotation component

The box/zone/overlay drawing is one annotation function (`client/annotation.py`)
that takes plain data (frame array, detections, zones, status text) and returns an
annotated frame. **It is owned and implemented by the alert-system change (change 2,
for its snapshot handler), which lands before this one (change 3); the live feed
consumes that same function** rather than reimplementing it. If the changes are
applied out of order, building the annotation helper is a prerequisite for this
change's live feed.

**Why:** the POC duplicated near-identical OpenCV drawing in three files. A single
pure-ish function (depends on cv2 but not on globals) is testable with literal
numpy fixtures and removes the duplication risk. Locating it in the client (not
`shared/`) keeps the server free of any drawing/UI concern.
This is flagged in the proposal as a cross-change shared concern so change 2
adopts it rather than re-duplicating.

### Lightweight-on-Pi-3B measures

- Bound the MJPEG emission rate (the POC's ~30 fps cap is likely too high; pick a
  conservative default and make it configurable) so the encode loop does not
  saturate the CPU.
- Re-encode for the stream only when a new frame is available; serve a cached
  placeholder before the first frame.
- Prefer polling + small JSON payloads over persistent sockets.
- Run Flask single-process; the client pipeline runs in its own thread/loop, the
  web server in another, communicating only through the injected state object.

### Testing strategy

- Build the app via `create_app(fake_state, settings)` and exercise every route
  through Flask's `test_client()` — no real camera, no real socket.
- The injected `DashboardState` fake yields canned frames (numpy arrays) and
  scripted stats/alerts, including the "no frame yet" case for the live feed.
- The MJPEG generator is tested by consuming a bounded number of parts from the
  stream (inject a fake clock/limit so the generator terminates in tests).
- Zone write-back is tested against a temp TOML file: valid edit persists and
  reloads identically; invalid edit leaves the file untouched; non-existent zone
  edit returns not-found.
- The shared annotation component is tested with literal frame/detection/zone
  fixtures asserting it draws (e.g. output differs from input, correct color by
  elevated state) without asserting exact pixels.
- `--cov-fail-under=100`; carry forward the foundation's `exclude_lines`
  (`__repr__`, `if __name__ == '__main__'`, abstract methods). No `print()` —
  logging facade. Docstrings on public APIs. ruff clean.

## Risks / Trade-offs

- **MJPEG encode load on the Pi 3B** → Bound the stream frame rate (configurable,
  conservative default) and only re-encode on new frames; the feed is for spot
  checks, not 30 fps video.
- **TOML round-trip loses comments / clobbers file** → Write only the zones
  section via the typed writer, write atomically (temp + rename), and validate
  before writing; document that comments inside the zones block may not survive a
  web save.
- **Concurrent file edits (hand vs. web)** → Last-writer-wins; acceptable for a
  single-user home system, flagged as an open question.
- **Thread-safety between client writer and request readers** → Encapsulate the
  lock inside the injected state object; keep update/read methods small and
  copy-on-read for frames to avoid tearing.
- **Polling latency for stats** → Up to one poll interval of staleness; acceptable
  for a status panel; SocketIO remains an escape hatch.
- **Coverage pressure on streaming code** → Make the generator loop bounded/
  injectable (clock + max-iterations seam) so it terminates deterministically in
  tests instead of needing `pragma: no cover`.

## Migration Plan

Additive and greenfield — no existing UI to migrate. Deploy by adding `flask` to
the client dependencies and starting the web server thread from the client
entrypoint alongside the capture pipeline. Rollback is simply not starting the web
server; the detection pipeline is unaffected because the web layer only reads the
injected state and writes the (already file-backed) zone config.

## Open Questions

- Default bounded stream frame rate for the Pi 3B (POC used ~30 fps; likely lower).
- Whether the web server runs in a thread inside the client process or as a
  separate process reading shared state — thread is simpler and the assumed
  default; a separate process would need an IPC mechanism for the frame/state.
- Exact TOML write-back mechanism (typed config writer vs. a TOML library that
  preserves formatting) and how aggressively to preserve comments/ordering.
- Whether recent-alert history should be purely in-memory (lost on restart) or
  read from the alert-system's log once that change lands — in-memory bounded
  deque assumed for now.
- Coordination policy if a hand-edit and a web-edit race (currently
  last-writer-wins).
