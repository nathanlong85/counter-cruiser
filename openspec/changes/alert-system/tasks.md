## 1. Scaffolding & dependencies

- [x] 1.1 Create `counter_cruiser/client/alerts/` package and matching `tests/client/alerts/` tree
- [x] 1.2 Add an optional `RPi.GPIO` extra (e.g. `pi`/`gpio`) and an HTTP client dep (`requests` or `httpx`) to `pyproject.toml`; keep them out of the base client install
- [x] 1.3 Define the typed `AlertContext` (frame, detections as `BoundingBox` list, zone polygons, triggered zones, frame id) and the `AlertHandler` interface (`trigger`, `cleanup`)

## 2. Alert configuration (configuration capability)

- [x] 2.1 Write tests for alert config models: cooldown/GPIO/snapshot/log/notification groups, range validators (duty cycle 0-100, positive duration), provider restricted to `ntfy.sh`/`Pushover`, `extra='forbid'`, env override
- [x] 2.2 Implement the alert config models and wire them into the client settings schema
- [x] 2.3 Add example alert config to the client TOML template/fixtures

## 3. Deterrent control (deterrent-control)

- [x] 3.1 Write tests (GPIO seam mocked): burst drives pin HIGH then LOW for the configured duration, using the configured pin (corrected during design: button-press simulation, not PWM/duty-cycle/frequency)
- [x] 3.2 Write tests for must-not-fire-continuously: pin driven LOW after a normal burst and after the burst raises mid-way (error logged); trigger()/cleanup() never raise even when the underlying GPIO call fails
- [x] 3.3 Write tests for graceful degradation: missing/uninitializable `RPi.GPIO` disables the handler with a clear log and does not raise; disabled handler triggers are no-ops
- [x] 3.4 Write tests for cleanup: releases GPIO after init; safe when disabled/uninitialized
- [x] 3.5 Implement `DeterrentHandler` (isolated GPIO import seam, timed HIGH/LOW burst with always-stop guarantee, self-disable, cleanup)

## 4. Notifications (alert-notifications)

- [x] 4.1 Write tests for the `NotificationProvider` interface and message building (message identifies triggered zones)
- [x] 4.2 Write tests for `NtfyProvider` (HTTP mocked): posts message to configured topic; success path
- [x] 4.3 Write tests for `PushoverProvider` (HTTP mocked): posts message with user key + API token
- [x] 4.4 Write tests for failure tolerance: network error and non-success status are logged and do not raise; missing credentials/topic logs and skips delivery
- [x] 4.5 Implement the provider interface, `NtfyProvider`, `PushoverProvider`, and the config-selecting `NotificationHandler`

## 5. Recording: snapshot (alert-recording)

- [x] 5.1 Write tests (tmp_path) for snapshot save: timestamped JPEG written to the configured dir; JSON sidecar records timestamp, triggered zones, detection count, frame id
- [x] 5.2 Write tests for annotation: boxes + zones + timestamp overlaid when enabled; triggered zones drawn distinctly from idle zones; no overlay when both disabled
- [x] 5.3 Write tests for max-count cleanup: oldest images and their sidecars deleted when over cap; no deletion when under cap
- [x] 5.4 Write tests for missing-frame handling: logs and returns without writing or raising
- [x] 5.5 Implement the reusable annotation helper at `client/annotation.py` (pure cv2 drawing over plain data, no globals — this is the shared component the web-ui change consumes) and the `SnapshotHandler` that uses it

## 6. Recording: log (alert-recording)

- [x] 6.1 Write tests (tmp_path) for structured log append: record includes triggered zones, frame id, detection count; write failure is logged and does not raise
- [x] 6.2 Implement `LogHandler` using the logging facade

## 7. Alert dispatch (alert-dispatch)

- [x] 7.1 Write tests for per-zone cooldown: proceed when any zone is outside its window (and record last-alert for all triggered zones), suppress + log when all zones are within window, independent per-zone tracking
- [x] 7.2 Write tests for fan-out: all enabled (injected) handlers run once; disabled handlers skipped
- [x] 7.3 Write tests for failure isolation: one handler raising still runs the others, failure logged with handler identity
- [x] 7.4 Write tests for cleanup: all handlers cleaned up; one failing cleanup does not block the rest
- [x] 7.5 Implement `AlertManager` (injected handlers, instance-level per-zone cooldown map, synchronous isolated fan-out, isolated cleanup)

## 8. Integration with the client pipeline

- [x] 8.1 Write an integration-style test: when the debounce condition is met, the AlertManager is invoked with triggered zones + context and dispatches; a single elevated frame (debounce not met) does not invoke it
- [x] 8.2 Wire the client orchestration to construct enabled handlers from config and call the AlertManager on the debounced elevated event (replacing print-only), with cleanup on shutdown

## 9. Finalization

- [ ] 9.1 Run the full test suite; confirm 100% coverage (`--cov-fail-under=100`)
- [ ] 9.2 Run `ruff check` and `ruff format`; resolve all findings
- [ ] 9.3 Verify docstrings on all new public modules/classes/functions
- [ ] 9.4 Update root `CLAUDE.md` Architecture/Commands sections to reflect the alert system
