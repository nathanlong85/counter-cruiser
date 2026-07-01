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
