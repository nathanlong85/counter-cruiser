## Context

The foundation change delivers detection end-to-end and decides, with
consecutive-frame debouncing, when a dog is "elevated" on the counter — but it
only prints the result. This change adds the response: deter the dog and record
the event. The behavior is proven by the `no-diggity` POC (`client/alerts.py` and
`version/main.py`'s `trigger_alert`), but that code was ad-hoc — untyped config
dicts, `print()` logging, module-level GPIO import fallback, duplicated drawing
code, no tests, and unimplemented email/Telegram stubs. We re-build the behavior
cleanly here; no POC code is carried over verbatim.

Fixed constraints from the project and the foundation:

- **Hardware split**: a Raspberry Pi 3B owns the camera and the GPIO deterrent;
  inference runs on a separate LAN machine. Zone analysis and the debounce live
  on the client (Pi) per the foundation design.
- **Quality gates**: 100% automated coverage (`--cov-fail-under=100`), ruff lint
  + format clean, docstrings on public APIs, no `print()` (logging facade), no
  module-level mutable state, dependency injection throughout.
- **Reuse**: `BoundingBox` comes from `detection-protocol`; alert config extends
  the client `configuration` schema (pydantic-settings, `extra='forbid'`); the
  debounce from `zone-analysis` is the trigger.

## Goals / Non-Goals

**Goals:**
- Fire an ultrasonic buzzer in short, bounded bursts to deter the dog, and never
  energize it continuously.
- Record each alert: annotated snapshot + JSON sidecar, structured log line, and
  a push notification.
- Per-zone cooldown to prevent repeat firing.
- Every handler testable headlessly by mocking GPIO, HTTP, and the filesystem, so
  the suite runs (and hits 100%) on a non-Pi dev machine.
- Graceful degradation: on a machine without `RPi.GPIO`, the deterrent disables
  itself with a clear log and the rest of the system runs normally.

**Non-Goals:**
- Email and Telegram notifications (POC had unimplemented stubs — excluded).
- Asynchronous or threaded handler execution.
- Arm/disarm ("I'm cooking") mode — parked as an open question, not specified.
- Changing any foundation behavior; this layers on top of the foundation's
  debounce, protocol, and config.
- The web UI's live annotation overlay (change 3) — though it will share the same
  annotation logic conceptually.

## Decisions

### Alerting runs on the client (Pi)

The AlertManager and all handlers live in the client package
(`counter_cruiser/client/alerts/`). The Pi owns the GPIO pins and the camera
frame, and the foundation already places zone analysis and the debounce
client-side. Putting alerting on the server would mean shipping the deterrent
decision back across the LAN and giving the server geometry/zone knowledge it was
deliberately kept free of. **Alternative considered:** server-side alerting —
rejected because the server is intentionally a stateless, zone-agnostic inference
service and does not own the GPIO.

### Handler abstraction

A small `AlertHandler` interface with `trigger(context)` and `cleanup()`. Concrete
handlers: `DeterrentHandler` (GPIO), `SnapshotHandler`, `LogHandler`, and
`NotificationHandler`. The `AlertManager` holds a list of injected, already-enabled
handlers and fans out to them. The alert context is a typed object carrying the
frame, detections (`BoundingBox` list), zone polygons, triggered zones, and frame
id — replacing the POC's untyped `alert_data` dict. **Why an interface:** uniform
fan-out, failure isolation, and cleanup; each handler is independently testable.

### Synchronous handler execution

Handlers run synchronously, in sequence. The per-zone cooldown bounds how often an
alert can fire (default 30 s), so the cost of a serial GPIO burst + file write +
HTTP POST is acceptable and far simpler than threads/async. **Alternative:**
async/threaded handlers — rejected as unnecessary complexity that would also
complicate the 100%-coverage testing story. Failure isolation is achieved by
wrapping each handler call in try/except and logging the failing handler, so one
bad handler never blocks the others.

### Cooldown design

Per-zone cooldown, configurable in seconds. The manager keeps a `{zone_id:
last_alert_time}` map (instance state, not module-level). An alert is suppressed
only when every triggered zone is still within its window; it proceeds if any
triggered zone is outside, and on proceeding the last-alert time is updated for
all triggered zones. **Why per-zone, not global:** different counter areas should
deter independently; a recent alert in zone A should not mute a first-time alert
in zone B. This matches the POC's `should_trigger` intent but with clearer
semantics.

### GPIO graceful degradation

`RPi.GPIO` sits behind an optional install extra; it is absent on the dev machine.
The import and hardware setup are isolated inside the `DeterrentHandler` (not a
module-level try/except as in the POC). If the library can't be imported or setup
fails, the handler disables itself, logs once, and all later triggers are no-ops —
never raising. This keeps the import seam injectable/patchable so tests can drive
both the available and unavailable paths to 100%. The burst is wrapped so the PWM
is always stopped (even on error) — the must-not-fire-continuously guarantee.

### Notification provider abstraction

One `NotificationProvider` interface with a `send(message)` method; two concrete
providers, `NtfyProvider` (HTTP POST to a topic URL, no account) and
`PushoverProvider` (HTTP POST with user key + API token). The handler selects the
provider from config and is otherwise provider-agnostic. Network/HTTP errors and
non-success statuses are caught and logged, never raised. **Why these two:**
ntfy.sh is free and frictionless for the common case; Pushover is the polished
paid option the user already used in the POC. Email/Telegram are dropped. **Why an
interface:** lets tests inject a fake provider and lets the HTTP layer be mocked
per provider.

### Snapshot annotation reuse

The snapshot handler annotates frames with boxes + zone polygons + timestamp using
OpenCV (already a client dep). The annotation logic is factored into a single
reusable function, **owned by this change** and located at
`counter_cruiser/client/annotation.py` (client-side — the server never draws —
importable by both `client/alerts/` and the change-3 `client/web/`). It takes plain
data (frame array, detections, zones, status/labels) and returns an annotated
frame, with no global state. Change 3 (web UI) consumes this same function for its
live feed rather than reimplementing it. Triggered zones are drawn distinctly from
idle zones. Max-count cleanup deletes oldest images and their JSON sidecars
together.

### Configuration

Alert settings extend the client TOML config via pydantic-settings, consistent
with the foundation's `configuration` capability (`extra='forbid'`, field
validators, env overrides). Groups: cooldown seconds; GPIO (pin, frequency,
duration, duty cycle, enabled); snapshot (dir, max count, include boxes, include
zones, enabled); log (file path, enabled); notification (provider enum + topic /
credentials, enabled). Validators enforce sane ranges (e.g. duty cycle 0-100,
positive duration, provider restricted to the two supported values).

### Testing strategy

- **GPIO**: inject/patch the `RPi.GPIO` seam; tests cover burst-then-stop,
  stop-on-error, unavailable-library degradation, disabled no-op, and cleanup.
- **HTTP (notifications)**: mock the HTTP client; tests cover ntfy and Pushover
  success, missing credentials, network error, and non-success status.
- **Filesystem (snapshot/log)**: use `tmp_path`; tests cover JPEG + sidecar write,
  annotation on/off, triggered-zone styling, max-count cleanup, missing-frame
  handling, and log append + failure.
- **AlertManager**: fake handlers; tests cover cooldown proceed/suppress/per-zone,
  fan-out to enabled handlers, disabled skip, failure isolation, and cleanup
  isolation.
- Coverage enforced at 100%; genuinely unreachable lines use `pragma: no cover`
  consistent with the foundation's config.

## Risks / Trade-offs

- **Synchronous handlers add latency to the detection loop** → Mitigated by the
  cooldown bounding frequency and by keeping each handler fast; if a handler (e.g.
  a slow HTTP POST) ever blocks too long, it can be moved off the hot path later
  without changing the handler contract.
- **Mocking `RPi.GPIO` means the real hardware path is only lightly exercised** →
  Accept; we test our wrapper's logic and treat `RPi.GPIO` as a trusted boundary,
  validating real wiring manually on the Pi.
- **A wrong duty cycle / duration in config could over-drive the buzzer** →
  Mitigated by config validators (bounded duration and duty cycle) plus the
  always-stop-after-burst guarantee; continuous output is structurally impossible
  from a single trigger.
- **ntfy.sh is a public service with no auth on a topic** → Acceptable for a home
  deterrent; the topic name acts as a shared secret and notifications contain no
  sensitive data. Pushover is available when stronger delivery is wanted.
- **100% coverage pressure on error/degradation branches** → Mitigated by keeping
  GPIO/HTTP/FS behind real, injectable seams so each failure branch is honestly
  reachable in tests.

## Migration Plan

Greenfield addition on top of the foundation; nothing to migrate. Deployment: the
Pi installs the client with the optional `RPi.GPIO` extra; the dev machine installs
without it (deterrent self-disables). The client orchestration is wired to call
the AlertManager when the debounce condition is met instead of only printing
elevated/floor. Rollback is config-driven: disable individual handlers (or all of
them) in the client TOML to revert to detection-only behavior.

## Implementation Divergence

**Deterrent mechanism corrected from PWM to GPIO button-press simulation.**
This design.md (and `proposal.md`) describe the deterrent as an ultrasonic PWM
buzzer with `pin`/`frequency`/`duration`/`duty_cycle` config fields. During the
`/comet-design` brainstorming pass, this was corrected: the actual hardware is
an existing ultrasonic trainer with a physical button, and the Pi's role is to
simulate a momentary button press by driving a BCM GPIO pin **HIGH** for
`burst_duration_seconds` then **LOW** — not to generate a PWM tone itself.
`DeterrentConfig` therefore has `enabled`, `pin`, `burst_duration_seconds` only;
there is no `frequency`, `duty_cycle`, or `active_low` field anywhere in the
implementation.

The authoritative technical design is
`docs/superpowers/specs/2026-07-01-alert-system-design.md`, and the delta specs
under `specs/deterrent-control/spec.md` (and the sibling capability specs) were
written to match the corrected mechanism from the start — they were never
PWM-based. Only this `design.md` and `proposal.md` retain the original,
superseded PWM language, since they capture the pre-correction proposal as a
historical record of how the idea evolved. All 11 implementation tasks, their
tests, and the corrected delta specs consistently use the GPIO HIGH/LOW
button-press mechanism; there is no PWM code, test, or behavior anywhere in
`counter_cruiser/`.

This divergence is intentional and does not require further action beyond this
note: at archive time, this `design.md` and `proposal.md` are change-scoped
artifacts (not merged into main specs) and will be marked
`superseded-by-main-spec`, with the corrected `specs/*/spec.md` syncing to
`openspec/specs/` as the durable record.

## Open Questions

- **Arm/disarm mode** ("I'm cooking, don't alert"): raised but not confirmed by
  the user. A possible future addition — e.g. a config flag or a runtime toggle
  (web UI / physical button) that suppresses dispatch while armed-off. Deliberately
  NOT specified as a requirement in this change; revisit as a follow-up if wanted.
- Default cooldown value (POC used 30 s) — confirm during tuning.
- ~~Where the snapshot annotation helper should live~~ **Resolved**: it lives at
  `counter_cruiser/client/annotation.py`, is implemented by this change, and is
  consumed (not reimplemented) by the change-3 web UI live feed.
