## ADDED Requirements

### Requirement: Status JSON endpoint

The web server SHALL expose a JSON endpoint returning the current operational
status: detection state (floor or elevated and which zones are triggered), camera
FPS, round-trip latency, and server-connection status.

#### Scenario: Status is returned as JSON

- **WHEN** a client requests the status endpoint
- **THEN** the server returns a JSON object containing detection state, triggered zones, camera FPS, round-trip latency, and server-connection status

#### Scenario: Elevated detection state is reflected

- **WHEN** the latest analyzed frame is classified as elevated within one or more zones
- **THEN** the status reports the detection state as elevated together with the triggered zone identifiers

#### Scenario: Floor detection state is reflected

- **WHEN** the latest analyzed frame is not classified as elevated
- **THEN** the status reports the detection state as floor with no triggered zones

#### Scenario: Disconnected server is reflected

- **WHEN** the client's connection to the inference server is down
- **THEN** the status reports the server-connection status as disconnected

### Requirement: Recent alert history

The web server SHALL expose a recent alert history. The history SHALL be bounded
to a maximum number of entries, discarding the oldest when the limit is exceeded,
and each entry SHALL record its time, the triggered zones, and the originating
frame identifier.

#### Scenario: Recent alerts are returned newest-first

- **WHEN** a client requests the alert history
- **THEN** the server returns the recent alerts ordered most-recent first, each with its time, triggered zones, and frame identifier

#### Scenario: History is bounded

- **WHEN** more alerts are recorded than the configured maximum history size
- **THEN** the oldest alerts are discarded so the history never exceeds the maximum

#### Scenario: No alerts yet

- **WHEN** no alerts have been recorded
- **THEN** the server returns an empty alert history without erroring

### Requirement: Dashboard page

The web server SHALL serve an HTML dashboard page that presents the status, stats,
and recent alert history together with the live feed for at-a-glance monitoring
from a phone or laptop.

#### Scenario: Dashboard page is served

- **WHEN** a browser requests the dashboard page
- **THEN** the server returns an HTML page presenting status, stats, recent alerts, and the live feed

### Requirement: Encapsulated, injected UI state

The web server's view of status, stats, frame, and alert history SHALL be held in
an encapsulated state/service object that is injected into the application rather
than stored in module-level globals. The running client SHALL update this object
with the latest frame, stats, and detection results, and the web endpoints SHALL
read from it.

#### Scenario: Client updates and endpoints read the same injected state

- **WHEN** the client pushes a new frame, stats, and detection result into the injected UI state object
- **THEN** subsequent requests to the status, alert, and live-feed endpoints reflect those updated values

#### Scenario: Server is testable with injected fake state

- **WHEN** the web server is constructed in a test with a fake UI state object and no real camera or socket
- **THEN** all endpoints can be exercised through the test client using only the injected state

#### Scenario: No module-level mutable state

- **WHEN** the web server module is imported
- **THEN** it creates no module-level mutable state, requiring the UI state object to be supplied at application construction
