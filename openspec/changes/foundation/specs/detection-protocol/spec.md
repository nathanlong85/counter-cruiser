## ADDED Requirements

### Requirement: Typed message models

The system SHALL define the WebSocket message contract between client and server
as typed Pydantic models. Every message SHALL carry a discriminating type field
and a timestamp.

#### Scenario: Each message type is a distinct model

- **WHEN** a message is constructed for any supported type (frame, detection, error, ping, pong)
- **THEN** it is represented by a dedicated typed model with a fixed type discriminator

#### Scenario: Messages carry a timestamp

- **WHEN** any message is created
- **THEN** it includes a creation timestamp

### Requirement: Message serialization and deserialization

The system SHALL serialize message models to a transport string and deserialize
received strings back into the correct typed model based on the discriminator.

#### Scenario: Round-trip serialization preserves data

- **WHEN** a message model is serialized and then deserialized
- **THEN** the resulting model equals the original

#### Scenario: Deserialization selects the correct model by type

- **WHEN** a serialized message with a given type discriminator is deserialized
- **THEN** the system produces an instance of the model corresponding to that type

#### Scenario: Malformed payload is rejected

- **WHEN** a received string is not valid JSON or does not match any known message schema
- **THEN** the system raises a deserialization error rather than returning a partial or untyped object

#### Scenario: Unknown message type is rejected

- **WHEN** a received message has a type discriminator that is not recognized
- **THEN** the system raises a deserialization error naming the unknown type

### Requirement: Frame message encoding

The frame message SHALL transport a camera frame from client to server. The
client SHALL JPEG-encode the frame at a configurable quality and embed it in the
message together with a monotonically increasing frame identifier and the frame
dimensions.

#### Scenario: Encode a frame into a frame message

- **WHEN** the client encodes an image array with a frame id and JPEG quality
- **THEN** the resulting frame message contains the encoded image data, the frame id, the frame dimensions, and a timestamp

#### Scenario: Decode a frame message back to an image

- **WHEN** the server decodes a frame message
- **THEN** it recovers an image array equivalent in shape to the original frame along with the frame id and timestamp

#### Scenario: Encoding failure is surfaced

- **WHEN** the underlying JPEG encoder fails to encode a frame
- **THEN** the system raises an error rather than sending an empty or invalid frame message

### Requirement: Detection message contents

The detection message SHALL transport inference results from server to client.
It SHALL reference the originating frame id and contain zero or more bounding
boxes and the server-side processing time.

#### Scenario: Detection message references its frame

- **WHEN** the server produces a detection result for a frame
- **THEN** the detection message contains the same frame id as the frame it was computed from

#### Scenario: Bounding box structure

- **WHEN** a detection message contains a bounding box
- **THEN** the box exposes integer corner coordinates, a confidence score, a class id, and a class name

#### Scenario: Empty detection result

- **WHEN** the server detects no dogs in a frame
- **THEN** the detection message contains an empty list of boxes and is still a valid detection message

### Requirement: Error and health-check messages

The system SHALL define an error message for communicating processing failures
and ping/pong messages for connection health checks.

#### Scenario: Error message carries context

- **WHEN** the server fails to process a frame
- **THEN** it can produce an error message containing an error type, a human-readable message, and the related frame id when known

#### Scenario: Ping is answered with pong

- **WHEN** the server receives a ping message
- **THEN** it responds with a pong message that echoes the ping's timestamp
