# Comet Design Handoff

- Change: alert-system
- Phase: design
- Mode: compact
- Context hash: 7abe71d8ce258e86b6b4b9616c2cb607d4cc1fbcd005b5e792f2c0b63d34f5c2

Generated-by: comet-handoff.sh

OpenSpec remains the canonical capability spec. This handoff is a deterministic, source-traceable context pack, not an agent-authored summary.

## openspec/changes/alert-system/proposal.md

- Source: openspec/changes/alert-system/proposal.md
- Lines: 1-68
- SHA256: 30beaadbba3eece9c087559077d136877fe54fd318a64e4535ea85c6a666bebc

```md
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
```

## openspec/changes/alert-system/design.md

- Source: openspec/changes/alert-system/design.md
- Lines: 1-188
- SHA256: 5499707f2f8618385a3adcfed11f0a91bd8f65d893b2d805617a4782a12bf7a3

[TRUNCATED]

```md
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

```

Full source: openspec/changes/alert-system/design.md

## openspec/changes/alert-system/tasks.md

- Source: openspec/changes/alert-system/tasks.md
- Lines: 1-60
- SHA256: b208a60a8195c3ec7c2a652328377b6c526cc6f46f599f6cd7de4aad5b49641b

```md
## 1. Scaffolding & dependencies

- [ ] 1.1 Create `counter_cruiser/client/alerts/` package and matching `tests/client/alerts/` tree
- [ ] 1.2 Add an optional `RPi.GPIO` extra (e.g. `pi`/`gpio`) and an HTTP client dep (`requests` or `httpx`) to `pyproject.toml`; keep them out of the base client install
- [ ] 1.3 Define the typed `AlertContext` (frame, detections as `BoundingBox` list, zone polygons, triggered zones, frame id) and the `AlertHandler` interface (`trigger`, `cleanup`)

## 2. Alert configuration (configuration capability)

- [ ] 2.1 Write tests for alert config models: cooldown/GPIO/snapshot/log/notification groups, range validators (duty cycle 0-100, positive duration), provider restricted to `ntfy.sh`/`Pushover`, `extra='forbid'`, env override
- [ ] 2.2 Implement the alert config models and wire them into the client settings schema
- [ ] 2.3 Add example alert config to the client TOML template/fixtures

## 3. Deterrent control (deterrent-control)

- [ ] 3.1 Write tests (GPIO seam mocked): burst starts PWM at duty cycle, holds duration, then stops; uses configured pin/frequency
- [ ] 3.2 Write tests for must-not-fire-continuously: PWM stopped after a normal burst and stopped + error logged when the burst raises mid-way
- [ ] 3.3 Write tests for graceful degradation: missing/uninitializable `RPi.GPIO` disables the handler with a clear log and does not raise; disabled handler triggers are no-ops
- [ ] 3.4 Write tests for cleanup: releases GPIO after init; safe when disabled/uninitialized
- [ ] 3.5 Implement `DeterrentHandler` (isolated GPIO import seam, timed-burst PWM with always-stop guarantee, self-disable, cleanup)

## 4. Notifications (alert-notifications)

- [ ] 4.1 Write tests for the `NotificationProvider` interface and message building (message identifies triggered zones)
- [ ] 4.2 Write tests for `NtfyProvider` (HTTP mocked): posts message to configured topic; success path
- [ ] 4.3 Write tests for `PushoverProvider` (HTTP mocked): posts message with user key + API token
- [ ] 4.4 Write tests for failure tolerance: network error and non-success status are logged and do not raise; missing credentials/topic logs and skips delivery
- [ ] 4.5 Implement the provider interface, `NtfyProvider`, `PushoverProvider`, and the config-selecting `NotificationHandler`

## 5. Recording: snapshot (alert-recording)

- [ ] 5.1 Write tests (tmp_path) for snapshot save: timestamped JPEG written to the configured dir; JSON sidecar records timestamp, triggered zones, detection count, frame id
- [ ] 5.2 Write tests for annotation: boxes + zones + timestamp overlaid when enabled; triggered zones drawn distinctly from idle zones; no overlay when both disabled
- [ ] 5.3 Write tests for max-count cleanup: oldest images and their sidecars deleted when over cap; no deletion when under cap
- [ ] 5.4 Write tests for missing-frame handling: logs and returns without writing or raising
- [ ] 5.5 Implement the reusable annotation helper at `client/annotation.py` (pure cv2 drawing over plain data, no globals — this is the shared component the web-ui change consumes) and the `SnapshotHandler` that uses it

## 6. Recording: log (alert-recording)

- [ ] 6.1 Write tests (tmp_path) for structured log append: record includes triggered zones, frame id, detection count; write failure is logged and does not raise
- [ ] 6.2 Implement `LogHandler` using the logging facade

## 7. Alert dispatch (alert-dispatch)

- [ ] 7.1 Write tests for per-zone cooldown: proceed when any zone is outside its window (and record last-alert for all triggered zones), suppress + log when all zones are within window, independent per-zone tracking
- [ ] 7.2 Write tests for fan-out: all enabled (injected) handlers run once; disabled handlers skipped
- [ ] 7.3 Write tests for failure isolation: one handler raising still runs the others, failure logged with handler identity
- [ ] 7.4 Write tests for cleanup: all handlers cleaned up; one failing cleanup does not block the rest
- [ ] 7.5 Implement `AlertManager` (injected handlers, instance-level per-zone cooldown map, synchronous isolated fan-out, isolated cleanup)

## 8. Integration with the client pipeline

- [ ] 8.1 Write an integration-style test: when the debounce condition is met, the AlertManager is invoked with triggered zones + context and dispatches; a single elevated frame (debounce not met) does not invoke it
- [ ] 8.2 Wire the client orchestration to construct enabled handlers from config and call the AlertManager on the debounced elevated event (replacing print-only), with cleanup on shutdown

## 9. Finalization

- [ ] 9.1 Run the full test suite; confirm 100% coverage (`--cov-fail-under=100`)
- [ ] 9.2 Run `ruff check` and `ruff format`; resolve all findings
- [ ] 9.3 Verify docstrings on all new public modules/classes/functions
- [ ] 9.4 Update root `CLAUDE.md` Architecture/Commands sections to reflect the alert system
```

## openspec/changes/alert-system/specs/alert-dispatch/spec.md

- Source: openspec/changes/alert-system/specs/alert-dispatch/spec.md
- Lines: 1-108
- SHA256: 5cdc0ada970609da9bc5e8751f430537708ba4509a1b531b3f5ebb079e6217bc

[TRUNCATED]

```md
## ADDED Requirements

### Requirement: Trigger on the debounced elevated event

The AlertManager SHALL be invoked only when the foundation's consecutive-detection
debounce condition is met (sustained evidence across frames), not on a single
elevated frame. The triggering event SHALL carry the set of triggered zones and
the supporting context (frame image, detections, and zone polygons) needed by the
handlers.

#### Scenario: Debounced event dispatches an alert

- **WHEN** the debounce condition is met and the AlertManager is invoked with the triggered zones and supporting context
- **THEN** the AlertManager evaluates cooldown and fans the event out to its enabled handlers

#### Scenario: Single elevated frame does not dispatch

- **WHEN** an elevated frame occurs but the debounce condition is not yet met
- **THEN** the AlertManager is not invoked and no handler runs

### Requirement: Per-zone cooldown suppression

The AlertManager SHALL enforce a configurable per-zone cooldown measured in
seconds. An alert SHALL be suppressed when every triggered zone is still within
its cooldown window; the alert SHALL proceed when at least one triggered zone is
outside its cooldown window. When an alert proceeds, the last-alert time SHALL be
updated for each triggered zone.

#### Scenario: Alert proceeds when a zone is outside cooldown

- **WHEN** at least one triggered zone has no recent alert or its last alert was longer ago than the cooldown
- **THEN** the alert proceeds and the last-alert time is recorded for every triggered zone

#### Scenario: Alert suppressed when all zones are within cooldown

- **WHEN** every triggered zone had an alert more recently than the cooldown window
- **THEN** the alert is suppressed, no handler runs, and the suppression is logged

#### Scenario: Cooldown is tracked independently per zone

- **WHEN** one zone is within cooldown but a different triggered zone is outside its cooldown
- **THEN** the alert proceeds for the event

### Requirement: Synchronous fan-out to enabled handlers

The AlertManager SHALL invoke each enabled handler synchronously, one after
another, passing the alert context. The AlertManager SHALL NOT introduce
threading or asynchronous execution for handlers; bounded alert frequency from
the cooldown makes synchronous execution acceptable. Disabled handlers SHALL be
skipped.

#### Scenario: All enabled handlers run for an alert

- **WHEN** an alert proceeds past cooldown with multiple enabled handlers registered
- **THEN** each enabled handler's trigger is invoked once with the alert context

#### Scenario: Disabled handler is skipped

- **WHEN** a handler is registered but disabled
- **THEN** its trigger is not invoked

### Requirement: Handler failure isolation

The AlertManager SHALL isolate handler failures so that an exception raised by one
handler does not prevent the remaining handlers from running. Each handler failure
SHALL be logged with the failing handler's identity.

#### Scenario: One failing handler does not stop the others

- **WHEN** a handler raises an exception during an alert
- **THEN** the AlertManager logs the failure and still invokes every other enabled handler

#### Scenario: Failure is attributed to the handler

- **WHEN** a handler raises an exception during an alert
- **THEN** the logged error identifies which handler failed

### Requirement: Handler construction via dependency injection

The AlertManager SHALL receive its handlers as injected collaborators rather than
```

Full source: openspec/changes/alert-system/specs/alert-dispatch/spec.md

## openspec/changes/alert-system/specs/alert-notifications/spec.md

- Source: openspec/changes/alert-system/specs/alert-notifications/spec.md
- Lines: 1-66
- SHA256: c069a3d7360d6bffc3f05e4e0408fcabcf02cea2b2812845de6023a100ff5a71

```md
## ADDED Requirements

### Requirement: Common notification interface

The system SHALL define a single notification-provider interface that accepts an
alert message and delivers it via an HTTP request. Concrete providers SHALL
implement this interface so the notification handler is agnostic to the provider
in use.

#### Scenario: Handler delivers through the configured provider

- **WHEN** the notification handler is triggered by an alert
- **THEN** it builds an alert message and delegates delivery to the configured provider through the common interface

#### Scenario: Message describes the triggered zones

- **WHEN** the notification handler builds the alert message
- **THEN** the message identifies the triggered zone or zones for the alert

### Requirement: Provider selection by configuration

The system SHALL select the notification provider from configuration, supporting
`ntfy.sh` and `Pushover`. The required credentials or topic SHALL be read from
configuration for the selected provider. An unknown or misconfigured provider
SHALL be reported clearly without crashing the alert dispatch.

#### Scenario: ntfy.sh provider selected

- **WHEN** configuration selects the `ntfy.sh` provider with a topic
- **THEN** notifications are delivered by posting the message to that ntfy.sh topic

#### Scenario: Pushover provider selected

- **WHEN** configuration selects the `Pushover` provider with its user key and API token
- **THEN** notifications are delivered by posting the message to the Pushover API with those credentials

#### Scenario: Missing credentials are reported

- **WHEN** the selected provider's required credentials or topic are absent
- **THEN** the handler logs a clear message and does not attempt delivery rather than raising

### Requirement: Network-failure tolerance

The notification handler SHALL tolerate network and HTTP failures. A failed or
non-success delivery SHALL be logged and SHALL NOT raise out of the handler, so
that a notification failure cannot break the alert dispatch or other handlers.

#### Scenario: Network error is tolerated

- **WHEN** the HTTP request to the provider raises a network error
- **THEN** the handler logs the failure and returns without raising

#### Scenario: Non-success HTTP status is logged

- **WHEN** the provider responds with a non-success HTTP status code
- **THEN** the handler logs the failure including the status and returns without raising

### Requirement: Out-of-scope notification channels

The system SHALL NOT include email or Telegram notification channels in this
capability. Only ntfy.sh and Pushover SHALL be provided.

#### Scenario: Only supported providers are configurable

- **WHEN** configuration is validated for the notification provider
- **THEN** only `ntfy.sh` and `Pushover` are accepted as providers
```

## openspec/changes/alert-system/specs/alert-recording/spec.md

- Source: openspec/changes/alert-system/specs/alert-recording/spec.md
- Lines: 1-82
- SHA256: 3b60200c58baca09381018e78815755e84a6a5f97a5514725cb8f37c4d0ab353

[TRUNCATED]

```md
## ADDED Requirements

### Requirement: Annotated snapshot capture

The snapshot handler SHALL save the alert frame as a JPEG image. When configured
to do so, it SHALL annotate the saved image with the detection bounding boxes, the
zone polygons, and a timestamp before writing it. Triggered zones SHALL be visually
distinguished from non-triggered zones in the annotation.

#### Scenario: Snapshot is saved as JPEG

- **WHEN** the snapshot handler is triggered with an alert frame
- **THEN** it writes a timestamped JPEG image to the configured snapshot directory

#### Scenario: Annotation overlays boxes, zones, and timestamp

- **WHEN** the snapshot handler is configured to include boxes and zones and is triggered
- **THEN** the saved image is annotated with the detection bounding boxes, the zone polygons, and a timestamp

#### Scenario: Triggered zones are visually distinguished

- **WHEN** the saved image is annotated with zone polygons
- **THEN** zones that triggered the alert are drawn distinctly from zones that did not

#### Scenario: Annotation can be disabled

- **WHEN** the snapshot handler is configured to include neither boxes nor zones
- **THEN** the frame is saved without box or zone overlays

### Requirement: Snapshot metadata sidecar

The snapshot handler SHALL write a JSON metadata sidecar alongside each saved
image, recording at least the timestamp, the triggered zones, the detection
count, and the frame identifier.

#### Scenario: Metadata sidecar accompanies the image

- **WHEN** a snapshot image is saved
- **THEN** a JSON sidecar with the same base name records the timestamp, triggered zones, detection count, and frame identifier

### Requirement: Snapshot count cap with oldest-deleted cleanup

The snapshot handler SHALL cap the total number of stored snapshots at a
configured maximum. When saving a new snapshot would exceed the maximum, the
oldest snapshots SHALL be deleted along with their metadata sidecars until the
count is within the maximum.

#### Scenario: Oldest snapshots are removed when over the cap

- **WHEN** saving a new snapshot causes the stored snapshot count to exceed the configured maximum
- **THEN** the oldest snapshots are deleted, including their JSON sidecars, until the count is within the maximum

#### Scenario: No cleanup when under the cap

- **WHEN** the stored snapshot count is at or below the configured maximum after saving
- **THEN** no existing snapshots are deleted

### Requirement: Missing frame is handled

The snapshot handler SHALL tolerate being triggered without a frame: it SHALL log
the condition and return without raising rather than writing an invalid file.

#### Scenario: Trigger without a frame

- **WHEN** the snapshot handler is triggered and no frame is provided in the alert context
- **THEN** it logs the condition and returns without writing a file or raising

### Requirement: Structured alert log records

The log handler SHALL append a structured record for each alert to a configured
log file. Each record SHALL include the triggered zones, the frame identifier,
and the detection count.

#### Scenario: Alert is appended to the log file

- **WHEN** the log handler is triggered by an alert
- **THEN** it appends a structured record containing the triggered zones, frame identifier, and detection count to the configured log file

#### Scenario: Log failure does not break dispatch

```

Full source: openspec/changes/alert-system/specs/alert-recording/spec.md

## openspec/changes/alert-system/specs/deterrent-control/spec.md

- Source: openspec/changes/alert-system/specs/deterrent-control/spec.md
- Lines: 1-68
- SHA256: 95bb112122d09dd384a25d62b694a86d38f8f83ddc60dde8e61f443c59c6569a

```md
## ADDED Requirements

### Requirement: Timed-burst button-press simulation

The GPIO deterrent handler SHALL drive a configured BCM pin HIGH (active-high)
to simulate a momentary press of an existing ultrasonic trainer's button. On
each alert it SHALL hold the pin HIGH for a single burst of the configured
duration and SHALL drive the pin back LOW when the burst completes.

#### Scenario: Alert emits one bounded burst

- **WHEN** the deterrent handler is triggered by an alert
- **THEN** it drives the configured pin HIGH, holds for the configured burst duration, and then drives the pin LOW

#### Scenario: Output uses the configured pin

- **WHEN** the deterrent handler initializes the GPIO output
- **THEN** it configures the BCM pin from configuration

### Requirement: Must not fire continuously

The deterrent handler SHALL NOT leave the pin HIGH (button held pressed) after a
burst, because holding the trainer's button indefinitely is harmful to the dog.
Every burst SHALL be bounded by the configured duration and followed by driving
the pin LOW, even if an error occurs mid-burst.

#### Scenario: Output is always stopped after a burst

- **WHEN** a burst of the configured duration completes
- **THEN** the pin is driven LOW so the button is not left pressed

#### Scenario: Output is stopped even when the burst errors

- **WHEN** an error occurs while a burst is active
- **THEN** the handler drives the pin LOW and logs the error rather than leaving the button pressed

### Requirement: Graceful degradation when GPIO is unavailable

The deterrent handler SHALL degrade gracefully when the `RPi.GPIO` library or the
hardware is unavailable (for example, when running on the dev machine rather than
a Pi). In that case it SHALL disable itself, log a clear message, and SHALL NOT
raise; subsequent triggers SHALL be no-ops.

#### Scenario: Missing GPIO library disables the handler

- **WHEN** the deterrent handler is constructed and `RPi.GPIO` cannot be imported or initialized
- **THEN** the handler disables itself and logs a clear message instead of raising

#### Scenario: Disabled handler ignores triggers

- **WHEN** the deterrent handler has disabled itself due to unavailable GPIO and is then triggered
- **THEN** it performs no GPIO action and does not raise

### Requirement: GPIO resource cleanup

The deterrent handler SHALL release its GPIO resources on cleanup, driving the
pin LOW and releasing it. Cleanup SHALL be safe to call when the handler is
disabled or was never initialized.

#### Scenario: Cleanup releases GPIO resources

- **WHEN** the deterrent handler is cleaned up after having initialized GPIO
- **THEN** it drives the pin LOW and releases the GPIO resources

#### Scenario: Cleanup is safe when GPIO was never initialized

- **WHEN** the deterrent handler is cleaned up while disabled or uninitialized
- **THEN** cleanup completes without error
```

