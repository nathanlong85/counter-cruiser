# live-feed Specification

## Purpose
TBD - created by archiving change web-ui. Update Purpose after archive.
## Requirements
### Requirement: Annotated MJPEG live feed

The web server SHALL expose an HTTP endpoint that streams the current camera
frame as a multipart MJPEG response. Each streamed frame SHALL be the annotated
frame — the captured image with detection bounding boxes, enabled zone polygons,
and a status/FPS overlay drawn on it — so a browser can confirm camera aim and
observe detection in real time.

#### Scenario: Stream serves annotated frames

- **WHEN** a browser requests the live-feed endpoint while frames are being captured
- **THEN** the server returns a multipart `multipart/x-mixed-replace` response whose parts are JPEG-encoded annotated frames

#### Scenario: Detection box reflects elevated state by color

- **WHEN** the current frame's detection is classified as elevated versus on the floor
- **THEN** the detection bounding box is drawn red for elevated and green for not-elevated

#### Scenario: Zones and status overlay are drawn

- **WHEN** a frame is annotated for the stream
- **THEN** enabled zone polygons and a status/FPS overlay are drawn on the frame in addition to any detection boxes

### Requirement: Graceful handling of no available frame

The live feed SHALL handle the case where no camera frame has been captured yet
(e.g. at startup) without erroring or closing the connection. It SHALL serve a
placeholder until a real frame is available.

#### Scenario: No frame captured yet

- **WHEN** the live-feed endpoint is requested before any frame has been captured
- **THEN** the server serves a placeholder frame and the response remains open, beginning to serve real frames once capture produces one

### Requirement: Bounded stream frame rate

The live feed SHALL limit the rate at which frames are emitted to a bounded
maximum to protect the Raspberry Pi 3B's limited CPU, rather than emitting frames
as fast as possible.

#### Scenario: Emission rate is capped

- **WHEN** annotated frames are available faster than the configured maximum stream rate
- **THEN** the stream emits frames no faster than the bounded maximum rate

### Requirement: Shared frame-annotation logic

The live feed SHALL produce its annotated frames using the single shared
frame-annotation component (`client/annotation.py`, owned by the alert-system
capability), rather than carrying its own copy of the box/zone/overlay drawing
logic.

#### Scenario: Annotation produced by the shared component

- **WHEN** the live feed annotates a frame for streaming
- **THEN** it produces the annotated image via the shared annotation component given the frame, detections, zones, and status, without its own copy of the drawing logic

