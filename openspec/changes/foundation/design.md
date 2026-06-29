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
cleanly to a list of typed `Zone` models.

### Protocol: Pydantic discriminated union

Messages are Pydantic models with a literal `type` discriminator, combined into a
discriminated union so deserialization picks the right model automatically and
rejects unknown/malformed payloads. Frames are JPEG-encoded then base64'd into
JSON (carried over from the POC).

**Why:** typed models replace the POC's hand-built dicts + `MessageType` string
constants; the discriminated union gives us "reject unknown type" and "reject
malformed" for free, satisfying the protocol spec's failure scenarios.

**Known trade-off (base64-in-JSON):** base64 inflates frame payloads ~33% and
JSON parsing of large strings is not free. For a Pi 3B on a LAN sending
frame-skipped 640×480 JPEGs this is acceptable. Recorded as a risk below;
revisit only if latency proves too high.

### Transport: `websockets` + asyncio

Keep the `websockets` library and asyncio model from the POC. The client runs two
concurrent tasks (capture/send loop and receive loop). The server uses
`websockets.serve` with one handler coroutine per connection.

**Why:** it already worked in the POC, it's the right concurrency model for "send
frames while receiving results," and `pytest-asyncio` makes it testable. Adding a
reconnect supervisor loop around the connection addresses the POC's fatal flaw
(client exits on disconnect).

### Model abstraction

A `DetectionModel` protocol/ABC with a single `detect(frame) -> list[BoundingBox]`
method. One concrete implementation for the foundation: YOLO via `ultralytics`,
filtering to the dog class above the confidence threshold. Device is config-driven
(`auto` picks an accelerator if available, else CPU; explicit `cpu`/`cuda:0`/etc.
honored). Model loading happens once at server start.

**Why one model, not two:** the POC carried both YOLO and MobileNet-SSD; that
duplication added no value. We standardize on YOLOv8n (good CPU/accelerator
tradeoff). The ABC keeps the seam open for a second model later without committing
to it now (no speculative implementation — just the interface the pipeline needs).

### Zone analysis lives on the client

The server returns raw dog bounding boxes; the client owns zone polygons, the
point-in-polygon test, the elevated decision, and consecutive-frame debouncing.

**Why client-side:** the client already needs zones for the change-3 dashboard
overlay and owns the deterrent; keeping zones on the client makes the server a
stateless, zone-agnostic inference service that any client could reuse. This
resolves the open question from exploration — zones are client-owned, server is
dumb about geometry.

### Geometry as a pure, side-effect-free module

Point-in-polygon, size-ratio, and the elevated decision live in `shared` as pure
functions operating on typed inputs, independent of OpenCV's drawing/capture.
Containment uses `cv2.pointPolygonTest` but is wrapped so callers pass plain
data.

**Why:** pure functions are trivially testable to 100% with literal fixtures
(no camera, no model), which is exactly where most of the behavioral risk lives.

### Logging and no global state

Replace every `print()` with the standard `logging` module configured once at
entrypoint (structured/file logging is a change-2 concern; for now, console
handler). No module-level mutable state — components are classes constructed with
their config and collaborators injected.

**Why:** import-time side effects and module globals were the POC's biggest
testability blockers. Dependency injection + a logging facade make 100% coverage
reachable and let tests assert on log records instead of capturing stdout.

### Testing strategy

- **Camera:** abstract behind a small capture interface; tests inject a fake that
  yields canned frames (numpy arrays) and can simulate read failures.
- **WebSocket:** test client/server handlers against in-memory fakes / `websockets`
  test utilities; `pytest-asyncio` drives coroutines.
- **Model:** inject a fake `DetectionModel` returning scripted boxes; the real
  YOLO path is covered with the ultralytics call mocked (we test our adapter, not
  ultralytics itself).
- **Coverage:** `--cov-fail-under=100`; genuinely unreachable lines use
  `pragma: no cover` (the POC's `pyproject.toml` already excludes `__repr__`,
  `if __name__ == '__main__'`, abstract methods, etc. — carry that forward).

## Risks / Trade-offs

- **base64-in-JSON frame overhead** → Acceptable on a LAN with frame-skipping;
  if latency is too high, switch frame transport to binary WebSocket messages
  (out of scope now, isolated behind the protocol layer so it's a contained
  change).
- **Pi 3B resource limits** → Client deliberately does no inference and installs
  no PyTorch (server extra); capture + encode + send is within the Pi's budget.
- **ultralytics/torch on AMD GPU (ROCm)** → Support is chip-dependent; the
  `auto` device path falls back to CPU, so the server always runs even if the
  accelerator isn't usable. Device is config-overridable for tuning.
- **100% coverage pressure causing test-shaped code** → Mitigate by keeping the
  seams meaningful (real interfaces: capture, model, transport) rather than
  mocking internals; pure-function geometry carries the bulk of behavior and is
  honestly testable.
- **Mocking the real model means the YOLO adapter's real inference path is only
  lightly exercised** → Accept; we test that our adapter correctly filters by
  class/confidence and maps results, with ultralytics treated as a trusted
  boundary.

## Open Questions

- Exact default model variant (YOLOv8n assumed) and whether to pin a specific
  ultralytics weights file vs. let it auto-download on first run.
- Whether the consecutive-debounce parameters (history size, frame-id gap) should
  be configurable now or hardcoded with the POC's values (2-frame window) until
  tuning is needed.
- Reconnect backoff policy specifics (fixed interval vs. exponential) — spec
  requires retry/reconnect; the exact schedule is a tasks-level detail.
