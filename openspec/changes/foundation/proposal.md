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
