# Brainstorm Summary

- Change: alert-system
- Date: 2026-07-01

## Confirmed Technical Approach

The alert-system change builds on the foundation's debounced elevated-dog event
with a client-side (Pi) `AlertManager` that enforces a per-zone cooldown and
fans out synchronously to injected handlers, isolating each handler's
failures.

Key implementation decisions confirmed during brainstorming (supplementing/
correcting design.md):

1. **Deterrent mechanism (corrected from design.md's PWM assumption):** the
   Pi repurposes an existing ultrasonic dog trainer by simulating its
   momentary button press, not driving PWM/frequency itself. `DeterrentHandler`
   drives a BCM GPIO pin HIGH (active-high) for a configured
   `burst_duration_seconds` (default 1.5s), then LOW, wrapped in try/finally
   so the pin always returns LOW even on error. Config: `enabled`, `pin`,
   `burst_duration_seconds` — no `frequency`/`duty_cycle`. Graceful
   degradation, must-not-fire-continuously, and cleanup semantics from
   design.md are unchanged, just reworded from PWM to digital-pulse.
2. **Frame retention:** `ClientSession` gains a bounded ring buffer
   (`dict[frame_id, np.ndarray]`, capped e.g. at the last 30 frames, oldest
   evicted) populated in `_send_loop`, with a `get_frame(frame_id)` lookup
   used by `__main__.py` to build `AlertContext` with the exact frame that
   produced the triggering detection.
3. **Handler execution order:** `AlertManager` always runs the deterrent
   handler first, synchronously, before snapshot/log/notification handlers —
   because training feedback must be immediate or the dog won't associate the
   correction with the behavior.
4. **Notifications:** synchronous `requests` library, 3s timeout per call.
5. **Config defaults:** `cooldown_seconds=5` (down from originally proposed
   30s — must be short enough to re-correct quickly), deterrent
   `enabled=False` by default with `burst_duration_seconds=1.5`, snapshot
   `dir="./snapshots"` / `max_count=200` / annotation on, log
   `file="./alerts.log"`, notification `enabled=False` by default.

## Key Trade-offs and Risks

- Synchronous handler execution blocks the client's asyncio event loop
  briefly during an alert (GPIO burst + snapshot write + HTTP POST). Accepted
  per design.md's original rationale: cooldown bounds frequency, and running
  the deterrent first keeps the safety-critical path fast; slower handlers
  (snapshot/notification) can add latency without harming the training
  signal since the buzz already fired.
- Ring buffer adds bounded memory overhead to `ClientSession`; capacity
  chosen to comfortably exceed debounce window.
- GPIO signal polarity fixed as active-high per confirmed hardware wiring
  (no `active_low` config — user explicitly chose the fixed default over
  making it configurable, since it isn't needed yet).

## Testing Strategy

Unchanged from design.md's original plan: GPIO seam mocked (burst-then-stop,
stop-on-error, missing-library degradation, disabled no-op, cleanup), HTTP
mocked for notifications (success, missing credentials, network error,
non-success status), `tmp_path` for snapshot/log tests, fake handlers for
`AlertManager` (cooldown, fan-out, failure isolation, cleanup isolation).
100% coverage enforced (`--cov-fail-under=100`). New: ring buffer unit tests
(eviction at capacity, lookup hit/miss).

## Spec Patches

- `specs/deterrent-control/spec.md`: rewrite the "Timed-burst ultrasonic
  output" requirement and its two scenarios to describe an active-high
  digital GPIO pulse for a configured burst duration, instead of PWM at a
  configured frequency/duty cycle. The must-not-fire-continuously, graceful
  degradation, and cleanup requirements are retained with wording updated
  from "PWM" to "GPIO output" where applicable.
