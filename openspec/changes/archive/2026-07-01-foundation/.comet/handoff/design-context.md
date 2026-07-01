# Comet Design Handoff

- Change: foundation
- Phase: design
- Mode: compact
- Context hash: c760177a77d0cce093bf3b0f54a6ebfd48722f36223fea90808a8e8e743d07d4

Generated-by: comet-handoff.sh

OpenSpec remains the canonical capability spec. This handoff is a deterministic, source-traceable context pack, not an agent-authored summary.

## openspec/changes/foundation/proposal.md

- Source: openspec/changes/foundation/proposal.md
- Lines: 1-68
- SHA256: beeb14cc5628e5fc62e7224027f791c2bfe1dc6d51063ae4839e5df3ed5e69bb

```md
## Why

counter-cruiser is a ground-up rewrite of the `no-diggity` proof-of-concept: a
system that detects when a dog climbs onto a kitchen counter and deters it. The
POC proved the concept works but was built ad-hoc — untyped config dicts,
`sys.path` import hacks, no tests, duplicated drawing code, and silent
import-fallback logic. This change establishes a clean, tested, well-typed
foundation that everything else builds on.

The deployment reality drives the architecture: a Raspberry Pi 3B is too weak to
run modern object detection in real time, but it has the camera and the GPIO
pins for the deterrent. So inference is offloaded to a more capable machine on
the same LAN. This change delivers the end-to-end detection pipeline across that
split — capture on the Pi, inference on the server, results back to the Pi —
with zone analysis determining whether a detected dog is actually "on the
counter."

## What Changes

- Establish a proper installable Python package (`counter_cruiser`) with `uv`,
  replacing all `sys.path.append` hacks and import-fallback mocking.
- Introduce a typed configuration system backed by TOML files and validated with
  `pydantic-settings`, replacing untyped `CONFIG` dicts.
- Introduce a typed WebSocket message protocol using Pydantic models, replacing
  hand-built dicts and `MessageType` string constants.
- Implement the detection pipeline end-to-end:
  - **Pi client**: capture frames from a USB webcam, JPEG-encode, frame-skip,
    send over WebSocket, receive detection results, reconnect on disconnect.
  - **Inference server**: receive frames, run a configurable detection model
    (YOLO via ultralytics) on a configurable device (`auto`/`cpu`/`cuda`/etc.),
    return bounding boxes.
- Implement zone analysis: polygon zones, point-in-polygon testing, and the
  "elevated" decision (dog is large enough AND inside an enabled zone), plus
  consecutive-detection debouncing.
- Establish project-wide quality gates: `ruff` lint + format, `pytest` with
  `pytest-asyncio`, and 100% coverage enforced in CI config.
- The foundation's observable result: the system connects, detects a dog in a
  frame, runs zone analysis, and reports "elevated / floor" to the console.

## Capabilities

### New Capabilities
- `configuration`: Typed, validated, file-based configuration for both the Pi
  client and the inference server, with environment-variable overrides and
  sensible defaults.
- `detection-protocol`: The WebSocket message contract between client and
  server — typed message models, serialization, and frame encode/decode.
- `detection-pipeline`: Frame capture, transport, model inference, reconnection,
  and the orchestration that ties client and server together end-to-end.
- `zone-analysis`: Polygon zone definitions, point-in-polygon containment, the
  elevated-dog decision, and consecutive-frame debouncing.

### Modified Capabilities
<!-- None — greenfield project, no existing specs. -->

## Impact

- **New package**: `counter_cruiser/` with `client/`, `server/`, `shared/`, and
  `config/` subpackages; corresponding `tests/` tree.
- **Dependencies**: `pydantic`, `pydantic-settings`, `websockets`, `opencv-python`,
  `numpy`, `ultralytics`/`torch` (server only, optional extra), plus the existing
  dev stack (`pytest`, `pytest-asyncio`, `pytest-cov`, `ruff`).
- **Hardware**: targets Pi 3B (client) + a Linux inference host (server) on the
  same LAN; USB webcam; GPIO buzzer wiring is defined in a later change.
- **Out of scope** (later changes): alert system (GPIO buzzer, snapshots, push
  notifications, logging) and the web UI (live feed, zone calibration, status).
- **Reference only**: the `no-diggity` repo informs behavior but no code is
  carried over verbatim.
```

## openspec/changes/foundation/design.md

- Source: openspec/changes/foundation/design.md
- Lines: 1-196
- SHA256: 9a9760d41038d5c0c98cded5ef53144a8e48d4bc7abedaa534b0b029b0fc6d3c

[TRUNCATED]

```md
---
comet_change: foundation
role: technical-design
canonical_spec: openspec
---

## Context

counter-cruiser replaces the `no-diggity` POC. The POC worked but accreted bad
patterns: untyped `CONFIG` dicts, `sys.path.append` import hacks, module-level
mutable globals, ~80 lines of silent import-fallback mocks, duplicated OpenCV
drawing code, `print()`-based logging everywhere, and zero tests.

The hardware split is fixed: a Raspberry Pi 3B (1 GB RAM, weak CPU) owns the USB
camera and the GPIO deterrent; a more capable Linux host on the same LAN runs
inference. This change builds the foundation — package skeleton, typed config,
typed protocol, the end-to-end detection pipeline, and zone analysis — on top of
which the alert system (change 2) and web UI (change 3) are layered.

This is greenfield: no existing specs, no code to preserve. The constraint that
shapes everything is **100% automated test coverage**, which forces seams
(dependency injection, no import-time side effects, no global state) into the
design from the start.

## Goals / Non-Goals

**Goals:**
- A proper installable `counter_cruiser` package with no path hacks.
- Typed, validated, file-based configuration with env overrides.
- A typed WebSocket protocol that fails loudly on malformed input.
- End-to-end detection: Pi captures → server infers → Pi runs zone analysis →
  console reports elevated/floor.
- Resilient client connection (retry + reconnect).
- Every component testable headlessly with mocked camera, sockets, and model.
- 100% line/branch coverage, full ruff lint + format, docstrings throughout.

**Non-Goals:**
- GPIO buzzer, snapshots, push notifications, logging-to-file (change 2).
- Web UI, live MJPEG feed, web-based zone calibration (change 3).
- Model training or fine-tuning — we use a pretrained off-the-shelf model.
- Multi-camera support, audio, or recording.
- Authentication / TLS on the LAN link (out of scope for a trusted home LAN).

## Decisions

### Package layout

```
counter_cruiser/
├── shared/        # protocol models, geometry, common types
├── config/        # pydantic-settings schemas + TOML loading
├── client/        # camera capture, transport, zone analysis, orchestration
└── server/        # websocket server, model abstraction, device selection
tests/
├── shared/  config/  client/  server/
```

Single package, installed with `uv`. Server-only heavy deps (`torch`,
`ultralytics`) go behind an optional extra (e.g. `pip install
counter-cruiser[server]`) so the Pi never has to install PyTorch. The client
extra pulls only `opencv-python`, `numpy`, `websockets`, `pydantic`.

**Why:** one package keeps the shared protocol and config DRY across client and
server; extras keep the Pi's footprint small. Alternative — two separate
packages with a shared third — adds release/versioning overhead not worth it for
a personal project.

### Configuration: pydantic-settings + TOML

Config is modeled with `pydantic-settings.BaseSettings`. Precedence:
environment variables > TOML file > field defaults. `extra='forbid'` so unknown
keys fail loudly. Field validators enforce ranges (`jpeg_quality` 1-100,
`confidence_threshold` 0.0-1.0, polygon ≥ 3 points). Separate `ClientSettings`
and `ServerSettings`, sharing a small common base.

**Why TOML:** human-editable, comments allowed, standard in modern Python
(`pyproject.toml` already TOML). **Why pydantic-settings over plain dataclasses:**
free validation, env-var binding, and clear error messages — the user explicitly
deferred to best practice here, and validation-at-load is the single biggest
robustness win over the POC's dict soup. The `[[zones]]` array-of-tables maps
```

Full source: openspec/changes/foundation/design.md

## openspec/changes/foundation/tasks.md

- Source: openspec/changes/foundation/tasks.md
- Lines: 1-82
- SHA256: f654e77c420477bf64068d5512320ee2a684ebd4f842a8bdfbce009dfdc3cd64

[TRUNCATED]

```md
## 1. Project scaffolding & quality gates

- [ ] 1.1 Initialize `counter_cruiser` package with `uv`; create `client/`, `server/`, `shared/`, `config/` subpackages and matching `tests/` tree
- [ ] 1.2 Configure `pyproject.toml`: core deps (`pydantic`, `pydantic-settings`, `websockets`, `opencv-python`, `numpy`) and a `server` extra (`torch`, `ultralytics`)
- [ ] 1.3 Carry forward dev deps and ruff config from no-diggity (B, E, F, I, SIM, UP; single quotes; line-length 88)
- [ ] 1.4 Configure pytest (`pytest-asyncio`, markers, `--strict-markers`) and coverage with `--cov-fail-under=100` and the carried-over `exclude_lines`
- [ ] 1.5 Add a logging facade configured once at entrypoints (console handler); establish "no `print()`, no import-time side effects" convention

## 2. Shared geometry (zone-analysis: containment, elevated, aggregate)

- [ ] 2.1 Write tests for point-in-polygon containment: point inside, point outside, disabled zones ignored, multiple zones triggered
- [ ] 2.2 Implement `check_zones(box, zones)` using corners+center against enabled polygons
- [ ] 2.3 Write tests for the elevated decision: large+in-zone, large+outside, small+in-zone, size-ratio computation
- [ ] 2.4 Implement `analyze_dog_position` (size ratio vs. min, AND in-zone)
- [ ] 2.5 Write tests for aggregate frame analysis: any-elevated, zone union, no-detections
- [ ] 2.6 Implement `analyze_detections` aggregating per-frame results

## 3. Consecutive-detection debouncing (zone-analysis)

- [ ] 3.1 Write tests: two-in-window meets, single does not, too-far-apart does not, out-of-order ordered by frame id, history bounded
- [ ] 3.2 Implement bounded detection history + consecutive-elevated check

## 4. Protocol (detection-protocol)

- [ ] 4.1 Write tests for typed message models (frame, detection, error, ping, pong): each has type discriminator + timestamp
- [ ] 4.2 Implement Pydantic message models and `BoundingBox` model
- [ ] 4.3 Write tests for serialize/deserialize: round-trip equality, type-based dispatch, malformed rejected, unknown type rejected
- [ ] 4.4 Implement discriminated-union serialization/deserialization
- [ ] 4.5 Write tests for frame encode/decode: encode produces image+id+shape+timestamp, decode recovers equivalent image, encode failure raises
- [ ] 4.6 Implement JPEG encode/decode (base64-in-JSON) for frame messages
- [ ] 4.7 Write tests for error and ping/pong: error carries context, ping answered by pong echoing timestamp
- [ ] 4.8 Implement error and ping/pong helpers

## 5. Configuration (configuration)

- [ ] 5.1 Write tests for `Zone` model: valid zone loads, <3 points rejected, no-zones permitted
- [ ] 5.2 Implement `Zone` model with polygon validation
- [ ] 5.3 Write tests for client/server settings: correct fields present, type/range/unknown-key rejection, range validators
- [ ] 5.4 Implement `ClientSettings`, `ServerSettings`, shared base with `extra='forbid'` and field validators
- [ ] 5.5 Write tests for loading: default path, `COUNTER_CRUISER_CONFIG` override, missing file → defaults, env-var precedence
- [ ] 5.6 Implement TOML loading + precedence (env > file > defaults)
- [ ] 5.7 Add example TOML config files for client and server (used as test fixtures and user templates)

## 6. Server: model abstraction & device selection (detection-pipeline)

- [ ] 6.1 Write tests for the `DetectionModel` adapter: filters to dog class, excludes below-threshold, maps results to `BoundingBox` (ultralytics mocked)
- [ ] 6.2 Implement `DetectionModel` ABC and the YOLO/ultralytics adapter
- [ ] 6.3 Write tests for device selection: auto picks accelerator/falls back to CPU, explicit device honored
- [ ] 6.4 Implement device selection and one-time model load

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
```

Full source: openspec/changes/foundation/tasks.md

## openspec/changes/foundation/specs/configuration/spec.md

- Source: openspec/changes/foundation/specs/configuration/spec.md
- Lines: 1-101
- SHA256: 2bafdd718a484ce4b36accca4940a4b1219da1845b0bc8e8f1ca57f04a8de9d9

[TRUNCATED]

```md
## ADDED Requirements

### Requirement: File-based configuration loading

The system SHALL load configuration from a TOML file for each component (client
and server). The configuration file path SHALL be resolvable from a known
default location and overridable via an environment variable.

#### Scenario: Load configuration from default path

- **WHEN** a component starts and a configuration file exists at the default path
- **THEN** the system loads and parses the TOML file into a typed configuration object

#### Scenario: Override configuration path via environment variable

- **WHEN** the `COUNTER_CRUISER_CONFIG` environment variable points to a valid TOML file
- **THEN** the system loads configuration from that path instead of the default

#### Scenario: Missing configuration file falls back to defaults

- **WHEN** no configuration file exists at the resolved path
- **THEN** the system uses built-in default values for every setting and starts successfully

### Requirement: Typed and validated configuration

The system SHALL represent configuration as typed models validated at load time
using `pydantic-settings`. Invalid values SHALL cause a clear, fail-fast error
rather than a runtime failure later.

#### Scenario: Valid configuration produces a typed object

- **WHEN** a configuration file contains values of the correct types and ranges
- **THEN** the system produces a typed configuration object with those values

#### Scenario: Invalid value type is rejected at load

- **WHEN** a configuration value has the wrong type (e.g. a string where an integer is required)
- **THEN** the system raises a validation error identifying the offending field and the component exits without starting

#### Scenario: Out-of-range value is rejected at load

- **WHEN** a configuration value violates a documented constraint (e.g. `jpeg_quality` outside 1-100, `confidence_threshold` outside 0.0-1.0)
- **THEN** the system raises a validation error identifying the offending field and constraint

#### Scenario: Unknown configuration key is rejected

- **WHEN** a configuration file contains a key that is not part of the schema
- **THEN** the system raises a validation error naming the unknown key

### Requirement: Environment-variable overrides

The system SHALL allow individual configuration values to be overridden by
environment variables, taking precedence over file values, which take precedence
over built-in defaults.

#### Scenario: Environment variable overrides a file value

- **WHEN** a configuration value is set both in the TOML file and via its environment variable
- **THEN** the system uses the environment-variable value

#### Scenario: Precedence ordering

- **WHEN** a value is defined by a default, a file, and an environment variable
- **THEN** the environment variable wins, then the file value, then the default

### Requirement: Component-specific configuration schemas

The system SHALL define separate configuration schemas for the client and the
server, each containing only the settings relevant to that component, plus a
shared schema for settings common to both.

#### Scenario: Client configuration contains client settings

- **WHEN** the client loads its configuration
- **THEN** the configuration object exposes server connection, camera, frame-skip, JPEG quality, and zone-analysis settings

#### Scenario: Server configuration contains server settings

- **WHEN** the server loads its configuration
- **THEN** the configuration object exposes bind host/port, model selection, inference device, and confidence-threshold settings
```

Full source: openspec/changes/foundation/specs/configuration/spec.md

## openspec/changes/foundation/specs/detection-pipeline/spec.md

- Source: openspec/changes/foundation/specs/detection-pipeline/spec.md
- Lines: 1-140
- SHA256: 7bd111d2b55de2324503d1f10013a446a25ce6c1436a4da7d995615f9e90fd05

[TRUNCATED]

```md
## ADDED Requirements

### Requirement: Camera frame capture

The client SHALL capture frames from a configured USB camera at a configured
resolution. It SHALL fail fast with a clear error if the camera cannot be opened
or produces no frames.

#### Scenario: Camera opens and produces frames

- **WHEN** the client starts with a valid camera index and resolution
- **THEN** it opens the camera, reads frames, and records the actual frame dimensions

#### Scenario: Camera cannot be opened

- **WHEN** the configured camera cannot be opened
- **THEN** the client raises a clear error and does not enter the capture loop

#### Scenario: Camera read failure during capture

- **WHEN** a frame read fails transiently during the capture loop
- **THEN** the client logs the failure and continues attempting to read rather than crashing

### Requirement: Frame skipping

The client SHALL send only every Nth captured frame to the server, where N is
the configured frame-skip value, to bound bandwidth and server load.

#### Scenario: Only every Nth frame is sent

- **WHEN** the frame-skip value is N and the client captures a sequence of frames
- **THEN** the client sends one frame to the server for every N frames captured

#### Scenario: Frame-skip of one sends every frame

- **WHEN** the frame-skip value is 1
- **THEN** the client sends every captured frame

### Requirement: Frame transport and result handling

The client SHALL send encoded frames to the server over a WebSocket connection
and concurrently receive detection results, matching each result to its
originating frame.

#### Scenario: Frame sent and detection received

- **WHEN** the client sends a frame and the server returns a detection for that frame id
- **THEN** the client matches the detection to the frame and processes it

#### Scenario: Round-trip latency is measured

- **WHEN** a detection result arrives for a previously sent frame
- **THEN** the client computes the round-trip latency from send time to receipt

#### Scenario: Server error message is handled

- **WHEN** the client receives an error message from the server
- **THEN** the client logs the error and continues operating

### Requirement: Connection resilience

The client SHALL attempt to connect to the server and SHALL automatically
reconnect if the connection is lost, rather than exiting.

#### Scenario: Initial connection failure retries

- **WHEN** the server is unreachable at startup
- **THEN** the client retries the connection on a backoff interval instead of exiting

#### Scenario: Reconnect after mid-session disconnect

- **WHEN** an established connection to the server drops during operation
- **THEN** the client stops sending, attempts to reconnect, and resumes sending once reconnected

#### Scenario: Graceful shutdown

- **WHEN** the client receives a shutdown signal
- **THEN** it releases the camera, closes the WebSocket connection, and exits cleanly

### Requirement: Server frame processing
```

Full source: openspec/changes/foundation/specs/detection-pipeline/spec.md

## openspec/changes/foundation/specs/detection-protocol/spec.md

- Source: openspec/changes/foundation/specs/detection-protocol/spec.md
- Lines: 1-100
- SHA256: 23c9fb1b479e57c4eb9f988f6f128e56eba8634c3f12dea53712a7f975ae293b

[TRUNCATED]

```md
## ADDED Requirements

### Requirement: Typed message models

The system SHALL define the WebSocket message contract between client and server
as typed Pydantic models. Every message SHALL carry a discriminating type field
and a timestamp.

#### Scenario: Each message type is a distinct model

- **WHEN** a message is constructed for any supported type (frame, detection, error, ping, pong)
- **THEN** it is represented by a dedicated typed model with a fixed type discriminator

#### Scenario: Messages carry a timestamp

- **WHEN** any message is created
- **THEN** it includes a creation timestamp

### Requirement: Message serialization and deserialization

The system SHALL serialize message models to a transport string and deserialize
received strings back into the correct typed model based on the discriminator.

#### Scenario: Round-trip serialization preserves data

- **WHEN** a message model is serialized and then deserialized
- **THEN** the resulting model equals the original

#### Scenario: Deserialization selects the correct model by type

- **WHEN** a serialized message with a given type discriminator is deserialized
- **THEN** the system produces an instance of the model corresponding to that type

#### Scenario: Malformed payload is rejected

- **WHEN** a received string is not valid JSON or does not match any known message schema
- **THEN** the system raises a deserialization error rather than returning a partial or untyped object

#### Scenario: Unknown message type is rejected

- **WHEN** a received message has a type discriminator that is not recognized
- **THEN** the system raises a deserialization error naming the unknown type

### Requirement: Frame message encoding

The frame message SHALL transport a camera frame from client to server. The
client SHALL JPEG-encode the frame at a configurable quality and embed it in the
message together with a monotonically increasing frame identifier and the frame
dimensions.

#### Scenario: Encode a frame into a frame message

- **WHEN** the client encodes an image array with a frame id and JPEG quality
- **THEN** the resulting frame message contains the encoded image data, the frame id, the frame dimensions, and a timestamp

#### Scenario: Decode a frame message back to an image

- **WHEN** the server decodes a frame message
- **THEN** it recovers an image array equivalent in shape to the original frame along with the frame id and timestamp

#### Scenario: Encoding failure is surfaced

- **WHEN** the underlying JPEG encoder fails to encode a frame
- **THEN** the system raises an error rather than sending an empty or invalid frame message

### Requirement: Detection message contents

The detection message SHALL transport inference results from server to client.
It SHALL reference the originating frame id and contain zero or more bounding
boxes and the server-side processing time.

#### Scenario: Detection message references its frame

- **WHEN** the server produces a detection result for a frame
- **THEN** the detection message contains the same frame id as the frame it was computed from

#### Scenario: Bounding box structure

- **WHEN** a detection message contains a bounding box
- **THEN** the box exposes integer corner coordinates, a confidence score, a class id, and a class name
```

Full source: openspec/changes/foundation/specs/detection-protocol/spec.md

## openspec/changes/foundation/specs/zone-analysis/spec.md

- Source: openspec/changes/foundation/specs/zone-analysis/spec.md
- Lines: 1-107
- SHA256: 23e53c7bec95fcfc01fab5fb755983e18f9cd5db664b567f2cbe5e636a9bb9a6

[TRUNCATED]

```md
## ADDED Requirements

### Requirement: Point-in-polygon zone containment

The system SHALL determine which enabled zones a bounding box overlaps by testing
a representative set of box points (its four corners and its center) for
containment within each enabled zone polygon. Disabled zones SHALL be ignored.

#### Scenario: Box point inside a zone

- **WHEN** any of a box's corners or its center lies inside or on an enabled zone polygon
- **THEN** that zone is included in the box's set of triggered zones

#### Scenario: Box entirely outside all zones

- **WHEN** none of a box's representative points lie inside any enabled zone
- **THEN** the box triggers no zones

#### Scenario: Disabled zones are ignored

- **WHEN** a box overlaps a zone whose enabled flag is false
- **THEN** that zone is not included in the triggered zones

#### Scenario: A box may trigger multiple zones

- **WHEN** a box's representative points lie inside more than one enabled zone
- **THEN** all such zones are included in the triggered zones

### Requirement: Elevated-dog decision

The system SHALL classify a detected dog as "elevated" only when it is both large
enough relative to the frame and located within at least one enabled zone. Size
SHALL be measured as the ratio of the box height to the frame height and compared
against a configured minimum size ratio.

#### Scenario: Large dog inside a zone is elevated

- **WHEN** a dog's box-height-to-frame-height ratio exceeds the minimum size ratio and the box triggers at least one zone
- **THEN** the dog is classified as elevated and the triggered zones are reported

#### Scenario: Large dog outside all zones is not elevated

- **WHEN** a dog is large enough but triggers no zones
- **THEN** the dog is not classified as elevated

#### Scenario: Small dog inside a zone is not elevated

- **WHEN** a dog triggers a zone but its size ratio does not exceed the minimum
- **THEN** the dog is not classified as elevated

#### Scenario: Size ratio is computed from frame height

- **WHEN** a dog's box height and the frame height are known
- **THEN** the size ratio is the box height divided by the frame height

### Requirement: Aggregate frame analysis

The system SHALL analyze all detections in a frame and produce a single summary
indicating whether any dog is elevated and the union of all triggered zones.

#### Scenario: Any elevated dog marks the frame elevated

- **WHEN** at least one detection in a frame is classified as elevated
- **THEN** the frame summary reports elevated as true

#### Scenario: Triggered zones are unioned across detections

- **WHEN** multiple detections in a frame each trigger zones
- **THEN** the frame summary's triggered zones are the union of all elevated detections' zones

#### Scenario: No detections yields a not-elevated summary

- **WHEN** a frame contains no detections
- **THEN** the frame summary reports elevated as false with an empty set of triggered zones

### Requirement: Consecutive-detection debouncing

The system SHALL require sustained evidence before treating an elevated state as
actionable. It SHALL maintain a bounded history of recent frames and SHALL
consider the condition met only when at least two elevated frames occur within a
```

Full source: openspec/changes/foundation/specs/zone-analysis/spec.md

