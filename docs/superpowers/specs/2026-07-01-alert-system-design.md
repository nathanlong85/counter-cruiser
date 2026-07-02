---
comet_change: alert-system
role: technical-design
canonical_spec: openspec
archived-with: 2026-07-01-alert-system
status: final
---

# Alert System — Technical Design

## Context

The foundation change detects an elevated dog and debounces the signal
client-side, but only logs the result. This change adds the response: when
the debounce condition is met, an `AlertManager` fans out to handlers that
deter the dog (GPIO) and record/notify the human (snapshot, log,
notification). See `openspec/changes/alert-system/proposal.md` and
`design.md` for the full goals/non-goals, capability breakdown, and original
architecture decisions (client-side alerting, handler abstraction,
synchronous execution, per-zone cooldown, notification provider abstraction,
snapshot annotation reuse, configuration shape, testing strategy). This
document supplements that design with implementation-level decisions
resolved during brainstorming, and **corrects one architectural assumption**
in the original design.md: the deterrent mechanism.

## Deterrent Mechanism (correction)

design.md assumed the Pi drives an ultrasonic buzzer directly via PWM at a
configurable frequency/duty cycle. That assumption is wrong: the actual
hardware is an existing off-the-shelf ultrasonic dog trainer whose
momentary-press button is being replaced by Pi GPIO control. The Pi does not
generate the ultrasonic tone — it only needs to simulate a button press.

**Design:** `DeterrentHandler.trigger()` drives a configured BCM pin HIGH
(active-high — confirmed against the actual wiring) for a configured
`burst_duration_seconds`, then drives it LOW. The burst is wrapped in
`try/finally` so the pin is always returned LOW even if an exception occurs
mid-burst — preserving the must-not-fire-continuously guarantee from the
original design (holding the button pressed indefinitely is harmful, same as
continuous ultrasonic output would have been). GPIO graceful degradation
(missing `RPi.GPIO`/hardware) and cleanup semantics are otherwise unchanged
from design.md — just reworded from "stop PWM" to "drive pin LOW."

Config fields: `enabled: bool` (default `False`), `pin: int` (BCM, required
when enabled), `burst_duration_seconds: float` (positive, default `1.5`).
There is no `frequency` or `duty_cycle` field, and no `active_low` toggle —
the hardware wiring is fixed active-high, and per YAGNI this isn't made
configurable since it isn't needed.

A Spec Patch was written back to
`openspec/changes/alert-system/specs/deterrent-control/spec.md`, replacing
the PWM/frequency/duty-cycle language in the "Timed-burst ultrasonic output"
(renamed "Timed-burst button-press simulation"), "Must not fire
continuously", and "GPIO resource cleanup" requirements with digital-pulse
language. Scope and requirement count are unchanged.

## Handler Execution Order

Training feedback must be immediate, or the dog will be confused about why
she's being corrected (the correction must follow the offending behavior
closely, not an unrelated few hundred milliseconds or seconds later). The
`AlertManager` therefore runs handlers in a fixed priority: the deterrent
handler always fires first, synchronously, before any other enabled handler.
Snapshot, log, and notification handlers run afterward in registration
order — their latency doesn't affect the training signal since the buzz has
already fired.

This refines (does not contradict) design.md's "Synchronous handler
execution" decision: handlers are still synchronous and sequential; this
adds a required ordering constraint (deterrent-first) on top.

## Frame Retention for Snapshots

**Gap in the original design:** `ClientSession` (in
`counter_cruiser/client/transport.py`) currently discards each captured frame
immediately after JPEG-encoding and sending it — `_send_loop` never retains
the raw frame, and the returning `DetectionMessage` carries only `frame_id`
and detection boxes, not image data. The snapshot handler needs the actual
frame for annotation, so a retention mechanism is required.

**Design:** `ClientSession` gains a bounded ring buffer,
`dict[int, np.ndarray]` keyed by `frame_id`, populated in `_send_loop`
immediately after each frame is captured (before encoding/sending). The
buffer is capped at a fixed capacity (e.g. the last 30 frames) with oldest
entries evicted once at capacity — comfortably larger than the debounce
window so the triggering frame is never evicted before the debounced event
fires. A new method, `get_frame(frame_id: int) -> np.ndarray | None`, exposes
lookup; `None` if the frame_id is unknown or already evicted (handled by the
snapshot handler's existing missing-frame tolerance).

`__main__.py`'s `on_result` callback uses `session.get_frame(msg.frame_id)`
when building the `AlertContext` for the debounced elevated event, alongside
the detections and triggered zones already available from
`analyze_detections`.

This is the authentic evidence frame from the moment of detection — not a
stale or re-captured frame — which matters for training-record accuracy: a
freshly re-captured frame at alert time could show the dog having already
reacted or moved off the counter.

## Notifications: HTTP Client

Notification handlers run synchronously inside the `AlertManager`'s fan-out
(per design.md's existing decision), so the HTTP call blocks the handler
(and therefore the client's event loop) briefly. `NtfyProvider` and
`PushoverProvider` use the synchronous `requests` library with a **3-second
timeout** per call, bounding how long a flaky network can stall alert
dispatch before the handler logs the failure and returns (per the
already-specified network-failure-tolerance requirement).

## Configuration Defaults

Resolved during brainstorming (supersedes any values implied by the original
proposal/design):

| Setting | Default |
|---|---|
| `cooldown_seconds` (per zone) | `5` |
| `deterrent.enabled` | `False` |
| `deterrent.pin` | required when enabled, no default |
| `deterrent.burst_duration_seconds` | `1.5` |
| `snapshot.dir` | `./snapshots` |
| `snapshot.max_count` | `200` |
| `snapshot.include_boxes` / `include_zones` | `True` / `True` |
| `log.file` | `./alerts.log` |
| `notification.enabled` | `False` |

The cooldown was deliberately lowered from an initially-proposed 30s to 5s:
training feedback needs to be able to re-fire quickly if the dog returns to
the counter shortly after a correction, rather than getting a multi-second
free pass.

## Testing Strategy

Unchanged from design.md's original plan — GPIO seam mocked (burst-then-stop,
stop-on-error, missing-library degradation, disabled no-op, cleanup), HTTP
mocked for notifications (success, missing credentials, network error,
non-success status), `tmp_path` for snapshot/log tests, fake handlers for
`AlertManager` (cooldown proceed/suppress/per-zone, fan-out including
deterrent-first ordering, failure isolation, cleanup isolation). Additions:

- GPIO burst tests assert pin driven HIGH then LOW (not PWM start/stop calls).
- `AlertManager` fan-out test explicitly asserts the deterrent handler's
  `trigger` is called before any other handler's.
- New unit tests for the frame ring buffer: eviction at capacity, lookup hit,
  lookup miss (unknown/evicted frame_id).
- 100% coverage enforced (`--cov-fail-under=100`), consistent with the
  project's existing quality gate.

## Risks / Trade-offs

- Synchronous handler execution briefly blocks the client's asyncio event
  loop during an alert (GPIO burst + snapshot write + HTTP POST). Accepted:
  cooldown bounds frequency, and deterrent-first ordering keeps the
  safety/training-critical path fast; slower handlers add latency without
  harming the training signal since the buzz already fired.
- The frame ring buffer adds bounded memory overhead to `ClientSession`;
  capacity is chosen to comfortably exceed the debounce window (foundation's
  `DetectionHistory` default `max_size=20`).
- Fixed active-high polarity assumes the wiring is correct; if wired
  backwards the trainer would fire continuously at idle (GPIO idle/boot state
  is LOW) rather than never firing — the safer failure mode was chosen as
  the fixed default, consistent with confirmed hardware wiring.
