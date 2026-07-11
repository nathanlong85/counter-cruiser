## ADDED Requirements

### Requirement: Expose operational status

The deterrent handler SHALL expose whether it is currently operational
(configured, enabled, and GPIO setup succeeded) so other components can
distinguish a healthy deterrent from one that silently disabled itself.

#### Scenario: Operational after successful GPIO setup

- **WHEN** the deterrent handler is constructed and GPIO setup succeeds
- **THEN** the handler reports itself as operational

#### Scenario: Not operational when GPIO is unavailable

- **WHEN** the deterrent handler is constructed and `RPi.GPIO` cannot be imported or GPIO setup fails
- **THEN** the handler reports itself as not operational

### Requirement: Record each trigger attempt's outcome

The deterrent handler SHALL record each attempted trigger's outcome
(succeeded or failed) for use by the deterrent usage-stats capability.

#### Scenario: A successful burst is recorded as succeeded

- **WHEN** a trigger's GPIO burst completes without error
- **THEN** the attempt is recorded as succeeded

#### Scenario: An erroring burst is recorded as failed

- **WHEN** a trigger's GPIO burst raises an error
- **THEN** the attempt is recorded as not succeeded, and the handler still drives the pin LOW as already required
