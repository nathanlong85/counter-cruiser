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
