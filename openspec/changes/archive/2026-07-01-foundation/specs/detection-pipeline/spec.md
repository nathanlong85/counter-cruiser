## ADDED Requirements

### Requirement: Camera frame capture

The client SHALL capture frames from a configured USB camera at a configured
resolution. It SHALL fail fast with a clear error if the camera cannot be opened
or produces no frames.

#### Scenario: Camera opens and produces frames

- **WHEN** the client starts with a valid camera index and resolution
- **THEN** it opens the camera, reads frames, and records the actual frame dimensions

#### Scenario: Camera cannot be opened

- **WHEN** the configured camera cannot be opened
- **THEN** the client raises a clear error and does not enter the capture loop

#### Scenario: Camera read failure during capture

- **WHEN** a frame read fails transiently during the capture loop
- **THEN** the client logs the failure and continues attempting to read rather than crashing

### Requirement: Frame skipping

The client SHALL send only every Nth captured frame to the server, where N is
the configured frame-skip value, to bound bandwidth and server load.

#### Scenario: Only every Nth frame is sent

- **WHEN** the frame-skip value is N and the client captures a sequence of frames
- **THEN** the client sends one frame to the server for every N frames captured

#### Scenario: Frame-skip of one sends every frame

- **WHEN** the frame-skip value is 1
- **THEN** the client sends every captured frame

### Requirement: Frame transport and result handling

The client SHALL send encoded frames to the server over a WebSocket connection
and concurrently receive detection results, matching each result to its
originating frame.

#### Scenario: Frame sent and detection received

- **WHEN** the client sends a frame and the server returns a detection for that frame id
- **THEN** the client matches the detection to the frame and processes it

#### Scenario: Round-trip latency is measured

- **WHEN** a detection result arrives for a previously sent frame
- **THEN** the client computes the round-trip latency from send time to receipt

#### Scenario: Server error message is handled

- **WHEN** the client receives an error message from the server
- **THEN** the client logs the error and continues operating

### Requirement: Connection resilience

The client SHALL attempt to connect to the server and SHALL automatically
reconnect if the connection is lost, rather than exiting.

#### Scenario: Initial connection failure retries

- **WHEN** the server is unreachable at startup
- **THEN** the client retries the connection on a backoff interval instead of exiting

#### Scenario: Reconnect after mid-session disconnect

- **WHEN** an established connection to the server drops during operation
- **THEN** the client stops sending, attempts to reconnect, and resumes sending once reconnected

#### Scenario: Graceful shutdown

- **WHEN** the client receives a shutdown signal
- **THEN** it releases the camera, closes the WebSocket connection, and exits cleanly

### Requirement: Server frame processing

The server SHALL accept client connections, decode incoming frames, run the
configured detection model, and return a detection message for each frame.

#### Scenario: Frame processed and result returned

- **WHEN** the server receives a valid frame message
- **THEN** it decodes the frame, runs detection, and returns a detection message referencing the frame id

#### Scenario: Processing error returns an error message

- **WHEN** processing a frame raises an exception
- **THEN** the server returns an error message referencing the frame id and continues serving the connection

#### Scenario: Multiple clients are isolated

- **WHEN** more than one client connects to the server
- **THEN** each connection is handled independently and a failure on one connection does not affect another

### Requirement: Configurable detection model and device

The server SHALL load a detection model selected by configuration and run it on a
configured compute device. It SHALL support automatic device selection and
explicit device selection (CPU or GPU).

#### Scenario: Automatic device selection

- **WHEN** the configured device is "auto"
- **THEN** the server selects an available accelerator if present and otherwise falls back to CPU

#### Scenario: Explicit device selection

- **WHEN** the configuration names a specific device
- **THEN** the server loads the model on that device

#### Scenario: Model identifies dogs only

- **WHEN** the model runs inference on a frame
- **THEN** only detections of the dog class above the confidence threshold are returned as bounding boxes

#### Scenario: Detection below confidence threshold is excluded

- **WHEN** a candidate detection has confidence below the configured threshold
- **THEN** it is excluded from the returned boxes

### Requirement: Pipeline reports detection outcome

The end-to-end pipeline SHALL combine server detections with client zone
analysis and report, per processed frame, whether an elevated dog was detected
and in which zones.

#### Scenario: Elevated dog reported

- **WHEN** a processed frame contains a dog that zone analysis classifies as elevated
- **THEN** the pipeline reports the frame as elevated together with the triggered zone identifiers

#### Scenario: Floor dog reported as not elevated

- **WHEN** a processed frame contains a dog that zone analysis does not classify as elevated
- **THEN** the pipeline reports the frame as not elevated
