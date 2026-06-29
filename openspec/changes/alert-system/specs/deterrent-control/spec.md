## ADDED Requirements

### Requirement: Timed-burst ultrasonic output

The GPIO deterrent handler SHALL drive an ultrasonic buzzer using PWM on a
configured BCM pin at a configured frequency and duty cycle. On each alert it
SHALL emit a single burst of the configured duration and SHALL stop the PWM
output when the burst completes.

#### Scenario: Alert emits one bounded burst

- **WHEN** the deterrent handler is triggered by an alert
- **THEN** it starts PWM at the configured duty cycle, holds for the configured duration, and then stops the PWM output

#### Scenario: Output uses the configured pin and frequency

- **WHEN** the deterrent handler initializes the GPIO output
- **THEN** it configures the BCM pin and PWM frequency from configuration

### Requirement: Must not fire continuously

The deterrent handler SHALL NOT leave the buzzer energized after a burst, because
continuous ultrasonic output is harmful to the dog. Every burst SHALL be bounded
by the configured duration and followed by stopping the output, even if an error
occurs mid-burst.

#### Scenario: Output is always stopped after a burst

- **WHEN** a burst of the configured duration completes
- **THEN** the PWM output is stopped so the buzzer is not left energized

#### Scenario: Output is stopped even when the burst errors

- **WHEN** an error occurs while a burst is active
- **THEN** the handler stops the PWM output and logs the error rather than leaving the buzzer energized

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

The deterrent handler SHALL release its GPIO resources on cleanup, stopping any
PWM and releasing the pin. Cleanup SHALL be safe to call when the handler is
disabled or was never initialized.

#### Scenario: Cleanup releases GPIO resources

- **WHEN** the deterrent handler is cleaned up after having initialized GPIO
- **THEN** it stops the PWM and releases the GPIO resources

#### Scenario: Cleanup is safe when GPIO was never initialized

- **WHEN** the deterrent handler is cleaned up while disabled or uninitialized
- **THEN** cleanup completes without error
