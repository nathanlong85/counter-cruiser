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
constructing them from module-level state, and the set of enabled handlers SHALL
be determined by configuration. There SHALL be no module-level mutable state.

#### Scenario: Handlers are provided to the manager

- **WHEN** the AlertManager is constructed with a configured set of handlers
- **THEN** it dispatches alerts only to those handlers

#### Scenario: Configuration selects which handlers are enabled

- **WHEN** configuration enables a subset of the available handler types
- **THEN** only the enabled handler types participate in dispatch

### Requirement: Cleanup on shutdown

The AlertManager SHALL provide a cleanup operation that releases every handler's
resources on shutdown. Cleanup of one handler SHALL NOT be prevented by another
handler's cleanup failure.

#### Scenario: Cleanup releases all handlers

- **WHEN** the AlertManager is cleaned up
- **THEN** each handler's cleanup is invoked

#### Scenario: A failing cleanup does not block other cleanups

- **WHEN** one handler's cleanup raises an exception
- **THEN** the failure is logged and the remaining handlers are still cleaned up
