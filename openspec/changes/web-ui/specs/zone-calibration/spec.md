## ADDED Requirements

### Requirement: View current zones

The web server SHALL expose the current zone definitions (identifier, display
name, enabled flag, and polygon points) plus a config version token, so the
calibration UI can render them over the live frame for editing and submit
that version with subsequent edit requests.

#### Scenario: Current zones are returned

- **WHEN** the calibration UI requests the current zones
- **THEN** the server returns each configured zone with its identifier, display name, enabled flag, and polygon points, together with a version token identifying the current state of the config file

#### Scenario: No zones configured

- **WHEN** the configuration defines no zones
- **THEN** the server returns an empty set of zones without erroring

### Requirement: Create and edit zones

The web server SHALL accept requests to create a new zone or edit an existing
zone's polygon, display name, or enabled flag. A created or edited polygon SHALL
be validated to contain at least three points, consistent with the foundation
`configuration` capability.

#### Scenario: Create a valid zone

- **WHEN** a request creates a zone with a name and a polygon of three or more points
- **THEN** the server adds the zone and reports success

#### Scenario: Edit an existing zone's polygon

- **WHEN** a request updates an existing zone's polygon to a new set of three or more points
- **THEN** the server replaces that zone's polygon with the new points

#### Scenario: Toggle a zone's enabled flag

- **WHEN** a request changes an existing zone's enabled flag
- **THEN** the server updates the zone's enabled state without altering its polygon

#### Scenario: Polygon with fewer than three points is rejected

- **WHEN** a create or edit request supplies a polygon with fewer than three points
- **THEN** the server rejects the request with a validation error and does not modify any zone

#### Scenario: Edit of a non-existent zone is rejected

- **WHEN** a request edits or deletes a zone identifier that does not exist
- **THEN** the server rejects the request with a not-found error and makes no change

### Requirement: Conflicting edit is rejected

The web server SHALL reject a create, edit, delete, or toggle request whose
submitted version token does not match the config file's current version,
without modifying the config file. This detects the config file having
changed (by a hand-edit or another web request) since the client last read
the zone set.

#### Scenario: Stale version is rejected

- **WHEN** a create, edit, delete, or toggle request submits a version token that does not match the config file's current version
- **THEN** the server rejects the request with a conflict error and does not modify the config file

### Requirement: Delete zones

The web server SHALL accept requests to delete an existing zone by its
identifier.

#### Scenario: Delete an existing zone

- **WHEN** a request deletes an existing zone by identifier
- **THEN** the server removes that zone and reports success

### Requirement: Persist zone edits to the client TOML config

The server SHALL persist the resulting zone set back to the client TOML
configuration file whenever a zone is created, edited, deleted, or toggled through
the web UI, so that the file remains the single source of truth and the change
survives a restart. Persistence SHALL only occur after validation succeeds.

#### Scenario: Successful edit is written to the config file

- **WHEN** a valid zone create, edit, delete, or toggle is applied
- **THEN** the updated zone set is written back to the client TOML configuration file

#### Scenario: Persisted zones reload consistently

- **WHEN** the client is restarted after a web-UI zone edit was persisted
- **THEN** the reloaded configuration contains the edited zones identical to what the web UI saved

#### Scenario: Rejected edit does not modify the config file

- **WHEN** a zone create or edit fails validation
- **THEN** the client TOML configuration file is left unchanged

### Requirement: Calibration runs against the live frame

The calibration UI SHALL present the current live frame as the backdrop for
drawing and editing zones so the user defines zones against what the camera
actually sees.

#### Scenario: Calibration page shows the live frame

- **WHEN** the user opens the zone calibration page
- **THEN** the page displays the current live frame as the backdrop for drawing and editing zone polygons
