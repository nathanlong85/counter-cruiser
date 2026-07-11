# deterrent-usage-stats Specification

## Purpose
TBD - created by archiving change deterrent-usage-stats. Update Purpose after archive.
## Requirements
### Requirement: Persistent deterrent trigger recording

The system SHALL persistently record every attempted deterrent trigger with
a timestamp and whether the attempt succeeded. Recorded events SHALL survive
a client restart.

#### Scenario: Successful attempt is recorded

- **WHEN** the deterrent handler attempts a trigger and the GPIO burst completes without error
- **THEN** an event is recorded with the current timestamp and marked as succeeded

#### Scenario: Failed attempt is recorded

- **WHEN** the deterrent handler attempts a trigger and the GPIO burst raises an error
- **THEN** an event is recorded with the current timestamp and marked as not succeeded

#### Scenario: Recorded events survive a restart

- **WHEN** the client is restarted after deterrent trigger events were recorded
- **THEN** previously recorded events remain available after restart

### Requirement: Day and week bucketed usage retrieval

The system SHALL provide deterrent trigger counts bucketed by day and by
week, based on recorded events.

#### Scenario: Day-bucketed counts are returned

- **WHEN** recorded events exist across multiple days
- **THEN** the system returns trigger counts grouped by day

#### Scenario: Week-bucketed counts are returned

- **WHEN** recorded events exist across multiple weeks
- **THEN** the system returns trigger counts grouped by week

#### Scenario: No events yet returns an empty result without erroring

- **WHEN** no deterrent trigger events have been recorded
- **THEN** the bucketed retrieval returns an empty result without erroring

### Requirement: Training-progress web page

The web server SHALL serve a dedicated page presenting the day/week bucketed
deterrent usage trend, the deterrent's current operational status, and
recent failure context if any recorded attempts failed.

#### Scenario: Training-progress page is served

- **WHEN** a browser requests the training-progress page
- **THEN** the server returns an HTML page presenting the bucketed usage trend and the deterrent's operational status

#### Scenario: Page reflects the no-events-yet state gracefully

- **WHEN** the training-progress page is requested before any deterrent trigger has been recorded
- **THEN** the page renders without erroring and indicates no corrections have been recorded yet

#### Scenario: Page surfaces recent failures

- **WHEN** one or more recorded events are marked as not succeeded
- **THEN** the training-progress page presents recent failure context alongside the usage trend

