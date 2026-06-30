## 1. Project scaffolding & quality gates

- [x] 1.1 Initialize `counter_cruiser` package with `uv`; create `client/`, `server/`, `shared/`, `config/` subpackages and matching `tests/` tree
- [x] 1.2 Configure `pyproject.toml`: core deps (`pydantic`, `pydantic-settings`, `websockets`, `opencv-python`, `numpy`) and a `server` extra (`torch`, `ultralytics`)
- [x] 1.3 Carry forward dev deps and ruff config from no-diggity (B, E, F, I, SIM, UP; single quotes; line-length 88)
- [x] 1.4 Configure pytest (`pytest-asyncio`, markers, `--strict-markers`) and coverage with `--cov-fail-under=100` and the carried-over `exclude_lines`
- [x] 1.5 Add a logging facade configured once at entrypoints (console handler); establish "no `print()`, no import-time side effects" convention

## 2. Shared geometry (zone-analysis: containment, elevated, aggregate)

- [x] 2.1 Write tests for point-in-polygon containment: point inside, point outside, disabled zones ignored, multiple zones triggered
- [x] 2.2 Implement `check_zones(box, zones)` using corners+center against enabled polygons
- [x] 2.3 Write tests for the elevated decision: large+in-zone, large+outside, small+in-zone, size-ratio computation
- [x] 2.4 Implement `analyze_dog_position` (size ratio vs. min, AND in-zone)
- [x] 2.5 Write tests for aggregate frame analysis: any-elevated, zone union, no-detections
- [x] 2.6 Implement `analyze_detections` aggregating per-frame results

## 3. Consecutive-detection debouncing (zone-analysis)

- [x] 3.1 Write tests: two-in-window meets, single does not, too-far-apart does not, out-of-order ordered by frame id, history bounded
- [x] 3.2 Implement bounded detection history + consecutive-elevated check

## 4. Protocol (detection-protocol)

- [x] 4.1 Write tests for typed message models (frame, detection, error, ping, pong): each has type discriminator + timestamp
- [x] 4.2 Implement Pydantic message models and `BoundingBox` model
- [x] 4.3 Write tests for serialize/deserialize: round-trip equality, type-based dispatch, malformed rejected, unknown type rejected
- [x] 4.4 Implement discriminated-union serialization/deserialization
- [x] 4.5 Write tests for frame encode/decode: encode produces image+id+shape+timestamp, decode recovers equivalent image, encode failure raises
- [x] 4.6 Implement JPEG encode/decode (base64-in-JSON) for frame messages
- [x] 4.7 Write tests for error and ping/pong: error carries context, ping answered by pong echoing timestamp
- [x] 4.8 Implement error and ping/pong helpers

## 5. Configuration (configuration)

- [x] 5.1 Write tests for `Zone` model: valid zone loads, <3 points rejected, no-zones permitted
- [x] 5.2 Implement `Zone` model with polygon validation
- [x] 5.3 Write tests for client/server settings: correct fields present, type/range/unknown-key rejection, range validators
- [x] 5.4 Implement `ClientSettings`, `ServerSettings`, shared base with `extra='forbid'` and field validators
- [x] 5.5 Write tests for loading: default path, `COUNTER_CRUISER_CONFIG` override, missing file → defaults, env-var precedence
- [x] 5.6 Implement TOML loading + precedence (env > file > defaults)
- [x] 5.7 Add example TOML config files for client and server (used as test fixtures and user templates)

## 6. Server: model abstraction & device selection (detection-pipeline)

- [x] 6.1 Write tests for the `DetectionModel` adapter: filters to dog class, excludes below-threshold, maps results to `BoundingBox` (ultralytics mocked)
- [x] 6.2 Implement `DetectionModel` ABC and the YOLO/ultralytics adapter
- [x] 6.3 Write tests for device selection: auto picks accelerator/falls back to CPU, explicit device honored
- [x] 6.4 Implement device selection and one-time model load

## 7. Server: websocket frame processing (detection-pipeline)

- [ ] 7.1 Write tests: valid frame → detection referencing frame id, processing error → error message + connection survives, multi-client isolation, ping→pong
- [ ] 7.2 Implement the connection handler and frame-processing flow (model injected)
- [ ] 7.3 Implement the server entrypoint (config-driven host/port/device, logging)

## 8. Client: capture & frame skipping (detection-pipeline)

- [ ] 8.1 Write tests (fake camera): opens+reads+records dims, open failure raises before loop, transient read failure continues
- [ ] 8.2 Implement the camera capture interface and a real OpenCV implementation
- [ ] 8.3 Write tests for frame skipping: every Nth sent, skip=1 sends all
- [ ] 8.4 Implement the capture/send loop with frame skipping

## 9. Client: transport, results & resilience (detection-pipeline)

- [ ] 9.1 Write tests: frame sent & detection matched, latency measured, server error handled
- [ ] 9.2 Implement the send + concurrent receive loops with frame/result matching and latency tracking
- [ ] 9.3 Write tests for resilience: initial-connect retry, mid-session reconnect resumes, graceful shutdown releases camera+socket
- [ ] 9.4 Implement the reconnect supervisor and graceful shutdown
- [ ] 9.5 Implement the client entrypoint wiring config, camera, transport, and zone analysis

## 10. End-to-end pipeline reporting (detection-pipeline)

- [ ] 10.1 Write an integration-style test (mocked camera + in-memory socket + fake model): elevated dog reported with zones, floor dog reported not-elevated
- [ ] 10.2 Wire detection results through zone analysis + debounce to a console report of elevated/floor per frame

## 11. Finalization

- [ ] 11.1 Run full test suite; confirm 100% coverage
- [ ] 11.2 Run `ruff check` and `ruff format`; resolve all findings
- [ ] 11.3 Verify docstrings on all public modules/classes/functions
- [ ] 11.4 Update root `CLAUDE.md` Architecture/Commands sections to reflect the real structure
