## ADDED Requirements

### Requirement: Point-in-polygon zone containment

The system SHALL determine which enabled zones a bounding box overlaps by testing
a representative set of box points (its four corners and its center) for
containment within each enabled zone polygon. Disabled zones SHALL be ignored.

#### Scenario: Box point inside a zone

- **WHEN** any of a box's corners or its center lies inside or on an enabled zone polygon
- **THEN** that zone is included in the box's set of triggered zones

#### Scenario: Box entirely outside all zones

- **WHEN** none of a box's representative points lie inside any enabled zone
- **THEN** the box triggers no zones

#### Scenario: Disabled zones are ignored

- **WHEN** a box overlaps a zone whose enabled flag is false
- **THEN** that zone is not included in the triggered zones

#### Scenario: A box may trigger multiple zones

- **WHEN** a box's representative points lie inside more than one enabled zone
- **THEN** all such zones are included in the triggered zones

### Requirement: Elevated-dog decision

The system SHALL classify a detected dog as "elevated" only when it is both large
enough relative to the frame and located within at least one enabled zone. Size
SHALL be measured as the ratio of the box height to the frame height and compared
against a configured minimum size ratio.

#### Scenario: Large dog inside a zone is elevated

- **WHEN** a dog's box-height-to-frame-height ratio exceeds the minimum size ratio and the box triggers at least one zone
- **THEN** the dog is classified as elevated and the triggered zones are reported

#### Scenario: Large dog outside all zones is not elevated

- **WHEN** a dog is large enough but triggers no zones
- **THEN** the dog is not classified as elevated

#### Scenario: Small dog inside a zone is not elevated

- **WHEN** a dog triggers a zone but its size ratio does not exceed the minimum
- **THEN** the dog is not classified as elevated

#### Scenario: Size ratio is computed from frame height

- **WHEN** a dog's box height and the frame height are known
- **THEN** the size ratio is the box height divided by the frame height

### Requirement: Aggregate frame analysis

The system SHALL analyze all detections in a frame and produce a single summary
indicating whether any dog is elevated and the union of all triggered zones.

#### Scenario: Any elevated dog marks the frame elevated

- **WHEN** at least one detection in a frame is classified as elevated
- **THEN** the frame summary reports elevated as true

#### Scenario: Triggered zones are unioned across detections

- **WHEN** multiple detections in a frame each trigger zones
- **THEN** the frame summary's triggered zones are the union of all elevated detections' zones

#### Scenario: No detections yields a not-elevated summary

- **WHEN** a frame contains no detections
- **THEN** the frame summary reports elevated as false with an empty set of triggered zones

### Requirement: Consecutive-detection debouncing

The system SHALL require sustained evidence before treating an elevated state as
actionable. It SHALL maintain a bounded history of recent frames and SHALL
consider the condition met only when at least two elevated frames occur within a
small frame-id window, tolerating a single-frame gap. The history SHALL be
robust to results arriving out of order.

#### Scenario: Two consecutive elevated frames meet the condition

- **WHEN** two elevated frames occur with frame ids differing by no more than the allowed gap
- **THEN** the debounce condition is met

#### Scenario: A single elevated frame does not meet the condition

- **WHEN** only one frame in the recent history is elevated
- **THEN** the debounce condition is not met

#### Scenario: Elevated frames too far apart do not meet the condition

- **WHEN** two elevated frames are separated by more than the allowed frame-id gap
- **THEN** the debounce condition is not met

#### Scenario: Out-of-order results are evaluated by frame id

- **WHEN** detection results arrive out of order
- **THEN** the debounce evaluation orders the history by frame id before checking the condition

#### Scenario: History is bounded

- **WHEN** the number of recorded frames exceeds the maximum history size
- **THEN** the oldest entries are discarded so the history never exceeds the maximum
