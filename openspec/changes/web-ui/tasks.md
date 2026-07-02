## 1. Scaffolding & dependencies

- [x] 1.1 Add `flask` to the client dependencies in `pyproject.toml` (keep `flask-socketio` out unless polling is later rejected)
- [x] 1.2 Create the `client/web/` subpackage (app factory, state, routes, zone writer, templates) and matching `tests/client/web/` tree (frame annotation is owned by the alert-system change at `client/annotation.py` and is imported, not recreated here)
- [x] 1.3 Confirm pytest/coverage config covers the new package (`--cov-fail-under=100`, carried-over `exclude_lines`); no `print()`, logging facade only

## 2. Frame annotation (consumed from alert-system)

- [x] 2.1 Confirm the shared `annotate_frame(frame, detections, zones, status)` component from `client/annotation.py` (implemented in the alert-system change) exposes what the live feed needs; if alert-system has not yet landed it, that is a sequencing prerequisite for this change
- [ ] 2.2 Write a test that the live feed calls the shared annotation component (asserts it is invoked with the current frame/detections/zones/status) rather than re-drawing — no second copy of the drawing logic in `client/web/`

## 3. Encapsulated UI state object

- [ ] 3.1 Write tests: update methods set frame/detections/stats/result; read methods return them; recent-alert history is bounded and newest-first; thread-safe copy-on-read of frame; "no frame yet" returns the no-frame sentinel
- [ ] 3.2 Implement the injected `DashboardState` object (internal lock, bounded alert deque, frame/stats/result holders); no module-level mutable state

## 4. App factory & test harness

- [ ] 4.1 Write tests: `create_app(state, settings)` builds an app exercisable via `test_client()` with a fake state and no real camera/socket
- [ ] 4.2 Implement `create_app(state, settings)` wiring the injected state into route handlers (app factory, no import-time side effects)

## 5. Status dashboard (status-dashboard)

- [x] 5.1 Write tests for the status JSON endpoint: returns detection state/triggered zones/FPS/latency/server status; elevated vs floor reflected; disconnected server reflected
- [x] 5.2 Implement the status JSON endpoint reading from the injected state
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
