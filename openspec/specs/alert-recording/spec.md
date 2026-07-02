# alert-recording Specification

## Purpose
TBD - created by archiving change alert-system. Update Purpose after archive.
## Requirements
### Requirement: Annotated snapshot capture

The snapshot handler SHALL save the alert frame as a JPEG image. When configured
to do so, it SHALL annotate the saved image with the detection bounding boxes, the
zone polygons, and a timestamp before writing it. Triggered zones SHALL be visually
distinguished from non-triggered zones in the annotation.

#### Scenario: Snapshot is saved as JPEG

- **WHEN** the snapshot handler is triggered with an alert frame
- **THEN** it writes a timestamped JPEG image to the configured snapshot directory

#### Scenario: Annotation overlays boxes, zones, and timestamp

- **WHEN** the snapshot handler is configured to include boxes and zones and is triggered
- **THEN** the saved image is annotated with the detection bounding boxes, the zone polygons, and a timestamp

#### Scenario: Triggered zones are visually distinguished

- **WHEN** the saved image is annotated with zone polygons
- **THEN** zones that triggered the alert are drawn distinctly from zones that did not

#### Scenario: Annotation can be disabled

- **WHEN** the snapshot handler is configured to include neither boxes nor zones
- **THEN** the frame is saved without box or zone overlays

### Requirement: Snapshot metadata sidecar

The snapshot handler SHALL write a JSON metadata sidecar alongside each saved
image, recording at least the timestamp, the triggered zones, the detection
count, and the frame identifier.

#### Scenario: Metadata sidecar accompanies the image

- **WHEN** a snapshot image is saved
- **THEN** a JSON sidecar with the same base name records the timestamp, triggered zones, detection count, and frame identifier

### Requirement: Snapshot count cap with oldest-deleted cleanup

The snapshot handler SHALL cap the total number of stored snapshots at a
configured maximum. When saving a new snapshot would exceed the maximum, the
oldest snapshots SHALL be deleted along with their metadata sidecars until the
count is within the maximum.

#### Scenario: Oldest snapshots are removed when over the cap

- **WHEN** saving a new snapshot causes the stored snapshot count to exceed the configured maximum
- **THEN** the oldest snapshots are deleted, including their JSON sidecars, until the count is within the maximum

#### Scenario: No cleanup when under the cap

- **WHEN** the stored snapshot count is at or below the configured maximum after saving
- **THEN** no existing snapshots are deleted

### Requirement: Missing frame is handled

The snapshot handler SHALL tolerate being triggered without a frame: it SHALL log
the condition and return without raising rather than writing an invalid file.

#### Scenario: Trigger without a frame

- **WHEN** the snapshot handler is triggered and no frame is provided in the alert context
- **THEN** it logs the condition and returns without writing a file or raising

### Requirement: Structured alert log records

The log handler SHALL append a structured record for each alert to a configured
log file. Each record SHALL include the triggered zones, the frame identifier,
and the detection count.

#### Scenario: Alert is appended to the log file

- **WHEN** the log handler is triggered by an alert
- **THEN** it appends a structured record containing the triggered zones, frame identifier, and detection count to the configured log file

#### Scenario: Log failure does not break dispatch

- **WHEN** writing the log record fails
- **THEN** the handler logs the failure and returns without raising

