## ADDED Requirements

### Requirement: File-based configuration loading

The system SHALL load configuration from a TOML file for each component (client
and server). The configuration file path SHALL be resolvable from a known
default location and overridable via an environment variable.

#### Scenario: Load configuration from default path

- **WHEN** a component starts and a configuration file exists at the default path
- **THEN** the system loads and parses the TOML file into a typed configuration object

#### Scenario: Override configuration path via environment variable

- **WHEN** the `COUNTER_CRUISER_CONFIG` environment variable points to a valid TOML file
- **THEN** the system loads configuration from that path instead of the default

#### Scenario: Missing configuration file falls back to defaults

- **WHEN** no configuration file exists at the resolved path
- **THEN** the system uses built-in default values for every setting and starts successfully

### Requirement: Typed and validated configuration

The system SHALL represent configuration as typed models validated at load time
using `pydantic-settings`. Invalid values SHALL cause a clear, fail-fast error
rather than a runtime failure later.

#### Scenario: Valid configuration produces a typed object

- **WHEN** a configuration file contains values of the correct types and ranges
- **THEN** the system produces a typed configuration object with those values

#### Scenario: Invalid value type is rejected at load

- **WHEN** a configuration value has the wrong type (e.g. a string where an integer is required)
- **THEN** the system raises a validation error identifying the offending field and the component exits without starting

#### Scenario: Out-of-range value is rejected at load

- **WHEN** a configuration value violates a documented constraint (e.g. `jpeg_quality` outside 1-100, `confidence_threshold` outside 0.0-1.0)
- **THEN** the system raises a validation error identifying the offending field and constraint

#### Scenario: Unknown configuration key is rejected

- **WHEN** a configuration file contains a key that is not part of the schema
- **THEN** the system raises a validation error naming the unknown key

### Requirement: Environment-variable overrides

The system SHALL allow individual configuration values to be overridden by
environment variables, taking precedence over file values, which take precedence
over built-in defaults.

#### Scenario: Environment variable overrides a file value

- **WHEN** a configuration value is set both in the TOML file and via its environment variable
- **THEN** the system uses the environment-variable value

#### Scenario: Precedence ordering

- **WHEN** a value is defined by a default, a file, and an environment variable
- **THEN** the environment variable wins, then the file value, then the default

### Requirement: Component-specific configuration schemas

The system SHALL define separate configuration schemas for the client and the
server, each containing only the settings relevant to that component, plus a
shared schema for settings common to both.

#### Scenario: Client configuration contains client settings

- **WHEN** the client loads its configuration
- **THEN** the configuration object exposes server connection, camera, frame-skip, JPEG quality, and zone-analysis settings

#### Scenario: Server configuration contains server settings

- **WHEN** the server loads its configuration
- **THEN** the configuration object exposes bind host/port, model selection, inference device, and confidence-threshold settings

### Requirement: Zone definitions in configuration

The system SHALL load polygon zone definitions from the client configuration.
Each zone SHALL have a stable identifier, a display name, an enabled flag, and a
polygon of at least three points.

#### Scenario: Valid zone definition is loaded

- **WHEN** the configuration contains a zone with a name, enabled flag, and a polygon of three or more points
- **THEN** the system loads the zone into the typed configuration

#### Scenario: Polygon with fewer than three points is rejected

- **WHEN** a zone polygon has fewer than three points
- **THEN** the system raises a validation error identifying the offending zone

#### Scenario: No zones defined is permitted

- **WHEN** the configuration defines no zones
- **THEN** the system loads successfully with an empty set of zones
