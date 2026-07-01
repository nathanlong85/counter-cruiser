## Why

The foundation change detects when a dog is "elevated" (on the counter) and
debounces that signal, but it only reports the result to the console — nothing
actually deters the dog or records the event. This change adds the alert system:
when the foundation's consecutive-detection debounce condition is met, fire an
ultrasonic buzzer to deter the dog and record/notify the human. The POC proved
these handlers (GPIO, snapshot, log, push notification) work; here we re-build
them cleanly — typed config, dependency injection, isolated failures, graceful
GPIO degradation, and 100% test coverage.

## What Changes

- Add an **AlertManager** that receives the foundation's debounced elevated
  event, enforces a per-zone cooldown, and fans out synchronously to all enabled
  handlers, isolating each handler's failures so one cannot break the others.
- Add a **GPIO buzzer deterrent** handler: ultrasonic PWM (~20 kHz) fired in
  short timed bursts (e.g. ~0.5 s) then stopped. It MUST NOT fire continuously
  (harmful to the dog). Degrades gracefully (disables itself with a clear log)
  when `RPi.GPIO` or the hardware is unavailable (e.g. on the dev machine).
- Add a **snapshot** handler: save an annotated frame (bounding boxes + zone
  polygons + timestamp) as JPEG with a JSON metadata sidecar, capping total
  snapshots with oldest-deleted cleanup.
- Add a **log** handler: append structured alert records to a log file.
- Add **push notifications** behind one interface, config-selectable between
  **ntfy.sh** (free, no account) and **Pushover** (paid app); network failures
  are tolerated. Email/Telegram are explicitly out of scope.
- Extend the **client TOML configuration** (pydantic-settings) with alert
  settings: cooldown, GPIO (pin/frequency/duration/duty-cycle), snapshot
  (dir/max-count/include-boxes/include-zones), log file, and notification
  (provider + credentials/topic).

## Capabilities

### New Capabilities
- `alert-dispatch`: AlertManager orchestration — receives the debounced elevated
  event, enforces per-zone cooldown, fans out to enabled handlers, isolates
  handler failures, and cleans up handlers on shutdown.
- `deterrent-control`: GPIO ultrasonic-buzzer handler — configurable timed-burst
  PWM with a must-not-fire-continuously guarantee and graceful degradation when
  GPIO is unavailable.
- `alert-notifications`: push notifications via ntfy.sh and Pushover behind one
  config-selected, network-failure-tolerant interface.
- `alert-recording`: snapshot (annotated JPEG + JSON metadata, max-count
  cleanup) and structured-log handlers.

### Modified Capabilities
<!-- None — these are net-new capabilities layered on the foundation; no existing
     foundation requirements change. -->

## Impact

- **New code**: alert handlers and the AlertManager in the client package
  (`counter_cruiser/client/alerts/`), with a matching `tests/` tree. New alert
  config models added to the client `configuration` schema.
- **Depends on foundation**: `zone-analysis` (the consecutive-detection debounce
  is the trigger), `detection-protocol` (`BoundingBox` for snapshot annotation),
  and `configuration` (client settings, pydantic-settings, `extra='forbid'`).
- **Wiring**: the client orchestration calls the AlertManager when the debounce
  condition is met instead of only printing elevated/floor.
- **Dependencies**: adds an optional `RPi.GPIO` extra (Pi-only; the GPIO handler
  degrades gracefully without it) and an HTTP client (`requests`/`httpx`) for
  notifications. Reuses `opencv-python`/`numpy` (already client deps) for
  snapshot annotation.
- **Runs on the Pi (client)**: the Pi owns the GPIO and camera, and zone
  analysis + debounce already live client-side per the foundation design.
- **Out of scope**: arm/disarm ("I'm cooking") mode is parked as an open
  question, not specified. Email/Telegram notifications are not included.
