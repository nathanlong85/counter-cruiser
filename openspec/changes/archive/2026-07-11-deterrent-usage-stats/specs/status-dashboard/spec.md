## ADDED Requirements

### Requirement: Deterrent usage summary on the dashboard

The dashboard page SHALL present a brief deterrent usage summary and a link
to the training-progress page, and SHALL reflect the deterrent's
operational status (not configured, configured and healthy, or configured
but broken).

#### Scenario: Dashboard shows a usage summary linking to the full page

- **WHEN** a browser requests the dashboard page
- **THEN** the page presents a brief deterrent usage summary and a link to the training-progress page

#### Scenario: Dashboard reflects an unconfigured deterrent

- **WHEN** the deterrent is not configured (disabled in configuration)
- **THEN** the dashboard indicates the deterrent is not configured, distinct from a health problem

#### Scenario: Dashboard reflects a broken deterrent

- **WHEN** the deterrent is configured and enabled but is not operational
- **THEN** the dashboard indicates the deterrent is configured but not currently operational
