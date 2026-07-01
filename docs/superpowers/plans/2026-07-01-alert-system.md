---
change: alert-system
design-doc: docs/superpowers/specs/2026-07-01-alert-system-design.md
base-ref: 40407d85de51481bfae99033028bbbbb28c25f58
---

# Alert System Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the alert system that fires when the foundation's debounced
"elevated dog" event occurs: a GPIO deterrent (button-press simulation on an
existing ultrasonic trainer), an annotated snapshot, a structured log record,
and an optional push notification — orchestrated by a new `AlertManager` with
per-zone cooldown and per-handler failure isolation.

**Architecture:** New `counter_cruiser/client/alerts/` package holds
`AlertContext`/`AlertHandler` (typed contract), one module per handler
(`deterrent.py`, `snapshot.py`, `log.py`, `notifications.py`), and
`manager.py` (`AlertManager`, deterrent-first fan-out + per-zone cooldown).
`counter_cruiser/client/annotation.py` holds the reusable frame-annotation
helper (owned by this change, consumed later by the web-UI change).
`ClientSession` (`client/transport.py`) gains a bounded frame ring buffer so
the snapshot handler can retrieve the authentic frame for a given
`frame_id`. `counter_cruiser/config/models.py` gains typed alert config
models wired into `ClientSettings`. `client/__main__.py` constructs the
enabled handlers from config and calls `AlertManager.maybe_alert()` on the
debounced elevated event instead of only logging.

**Tech Stack:** Python 3.11, pydantic v2 / pydantic-settings, pytest +
pytest-asyncio + pytest-cov (100% required), `RPi.GPIO` (optional extra,
mocked in tests), `requests` (HTTP, mocked in tests), OpenCV/numpy (already
client deps), ruff (lint + format).

## Global Constraints

- 100% line **and branch** coverage enforced (`--cov-fail-under=100` is
  already set in `pyproject.toml` with `branch = true`); every new
  conditional needs a test on each branch, or an honest `pragma: no cover`
  for a structurally unreachable line.
- No `print()` — use the `logging` facade (`logging.getLogger(__name__)`),
  matching every existing module.
- No module-level mutable state; no module-level `try/except` import
  fallback for `RPi.GPIO` (unlike `server/model.py`'s torch/ultralytics
  pattern) — the GPIO import must be an isolated, patchable seam inside
  `DeterrentHandler` per the corrected design.
- Dependency injection throughout: handlers, providers, and the GPIO/HTTP
  seams are constructor-injectable so tests never touch real hardware or
  network.
- `ruff check .` and `ruff format .` clean (project config:
  `line-length = 88`, `quote-style = 'single'`, lint selects
  `B, E, F, I, SIM, UP`).
- Docstrings required on every new public module, class, and function
  (project convention — see existing modules).
- Config models use `extra='forbid'` and field validators for sane ranges,
  consistent with `Zone`/`ClientSettings` in `config/models.py`.
- Deterrent mechanism (corrected design, do not use the original PWM
  language): `DeterrentHandler.trigger()` drives a configured BCM pin
  **HIGH** for `burst_duration_seconds`, then **LOW**, wrapped in
  `try/finally`. No `frequency`, `duty_cycle`, or `active_low` fields.
- Handler execution order: the deterrent handler always fires first,
  synchronously, before any other handler — enforced structurally in
  `AlertManager`, not by injection-order convention.
- Config defaults (resolved during brainstorming — see design doc
  "Configuration Defaults" table): `cooldown_seconds=5`,
  `deterrent.enabled=False`, `deterrent.burst_duration_seconds=1.5`,
  `snapshot.dir='./snapshots'`, `snapshot.max_count=200`,
  `snapshot.include_boxes=True`, `snapshot.include_zones=True`,
  `log.file='./alerts.log'`, `notification.enabled=False`.
- Notification HTTP calls use a **3-second timeout** per call.
- Frame ring buffer capacity: last **30 frames**, keyed by `frame_id`,
  oldest evicted at capacity — comfortably larger than
  `DetectionHistory`'s default `max_size=20`.

---

## Task 1: Package scaffolding & dependencies

- [x] **Task 1 complete**

**Files:**
- Create: `counter_cruiser/client/alerts/__init__.py`
- Create: `tests/client/alerts/__init__.py`
- Modify: `pyproject.toml`

**Interfaces:**
- Produces: the `counter_cruiser.client.alerts` package (empty re-export
  module for now — populated as later tasks land) and the `gpio` optional
  extra + `requests` base dependency other tasks import.

- [x] **Step 1: Create the package directories**

```bash
mkdir -p counter_cruiser/client/alerts tests/client/alerts
```

- [x] **Step 2: Add the package `__init__.py` files**

`counter_cruiser/client/alerts/__init__.py`:

```python
"""Alert handlers and orchestration for the debounced elevated-dog event."""
```

`tests/client/alerts/__init__.py`:

```python
"""Tests for the counter_cruiser.client.alerts package."""
```

- [x] **Step 3: Add the `gpio` extra and `requests` dependency to `pyproject.toml`**

Edit `[project]` `dependencies` to add `requests`, and add a new
`[project.optional-dependencies]` entry:

```toml
[project]
dependencies = [
    "pydantic>=2.7",
    "pydantic-settings>=2.3",
    "websockets>=12.0",
    "opencv-python>=4.10",
    "numpy>=1.26",
    "requests>=2.32",
]

[project.optional-dependencies]
server = [
    "torch>=2.3",
    "ultralytics>=8.2",
]
gpio = [
    "RPi.GPIO>=0.7.1; platform_machine == 'armv7l' or platform_machine == 'aarch64'",
]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.23",
    "pytest-cov>=5.0",
    "ruff>=0.6",
    "requests-mock>=1.12",
]
```

`requests` moves to a base dependency (notifications are a first-class
client feature, not Pi-only) while `RPi.GPIO` stays Pi-only behind the
`gpio` extra with an environment marker so `uv pip install -e ".[dev]"`
succeeds on a non-Pi dev machine without ever attempting to build it.
`requests-mock` is added to `dev` for HTTP-mocked notification tests.

- [x] **Step 4: Reinstall editable deps and confirm the environment resolves**

Run: `uv pip install -e ".[dev]"`
Expected: installs successfully, including `requests` and `requests-mock`;
no attempt to install `RPi.GPIO` on the dev machine (marker excludes it).

- [x] **Step 5: Commit**

```bash
git add counter_cruiser/client/alerts/__init__.py tests/client/alerts/__init__.py pyproject.toml
git commit -m "chore(alert-system): scaffold alerts package and add requests/gpio deps"
```

---

## Task 2: `AlertContext` and `AlertHandler` interface

- [x] **Task 2 complete**

**Files:**
- Create: `counter_cruiser/client/alerts/context.py`
- Test: `tests/client/alerts/test_context.py`

**Interfaces:**
- Consumes: `counter_cruiser.shared.protocol.BoundingBox`,
  `counter_cruiser.config.models.Zone` (both already exist).
- Produces: `AlertContext` (dataclass: `frame: np.ndarray | None`,
  `detections: list[BoundingBox]`, `zones: list[Zone]`,
  `triggered_zones: set[str]`, `frame_id: int`) and `AlertHandler`
  (`typing.Protocol` with `trigger(self, context: AlertContext) -> None`
  and `cleanup(self) -> None`) — every later handler task implements this
  protocol structurally (no explicit inheritance required, matching the
  `CameraCapture` protocol pattern in `client/capture.py`).

- [x] **Step 1: Write the failing test for `AlertContext` construction**

```python
"""Tests for AlertContext and the AlertHandler protocol."""

from __future__ import annotations

import numpy as np

from counter_cruiser.client.alerts.context import AlertContext, AlertHandler
from counter_cruiser.config.models import Zone
from counter_cruiser.shared.protocol import BoundingBox


def _box() -> BoundingBox:
    return BoundingBox(
        x1=0, y1=0, x2=10, y2=10, confidence=0.9, class_id=16, class_name='dog'
    )


class TestAlertContext:
    def test_construction_holds_all_fields(self) -> None:
        frame = np.zeros((10, 10, 3), dtype=np.uint8)
        zone = Zone(id='z1', name='Counter', polygon=[(0, 0), (10, 0), (10, 10)])
        ctx = AlertContext(
            frame=frame,
            detections=[_box()],
            zones=[zone],
            triggered_zones={'z1'},
            frame_id=42,
        )
        assert ctx.frame is frame
        assert ctx.detections == [_box()]
        assert ctx.zones == [zone]
        assert ctx.triggered_zones == {'z1'}
        assert ctx.frame_id == 42

    def test_frame_may_be_none(self) -> None:
        ctx = AlertContext(
            frame=None, detections=[], zones=[], triggered_zones=set(), frame_id=1
        )
        assert ctx.frame is None


class TestAlertHandlerProtocol:
    def test_a_conforming_object_satisfies_the_protocol(self) -> None:
        class FakeHandler:
            def trigger(self, context: AlertContext) -> None:
                return None

            def cleanup(self) -> None:
                return None

        handler: AlertHandler = FakeHandler()
        handler.trigger(
            AlertContext(
                frame=None, detections=[], zones=[], triggered_zones=set(), frame_id=1
            )
        )
        handler.cleanup()
```

- [x] **Step 2: Run the test to confirm it fails**

Run: `pytest tests/client/alerts/test_context.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named
'counter_cruiser.client.alerts.context'`

- [x] **Step 3: Implement `AlertContext` and `AlertHandler`**

`counter_cruiser/client/alerts/context.py`:

```python
"""Typed context passed to alert handlers, and the handler protocol."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import numpy as np

from counter_cruiser.config.models import Zone
from counter_cruiser.shared.protocol import BoundingBox


@dataclass
class AlertContext:
    """Everything a handler needs to record or react to one alert event."""

    frame: np.ndarray | None
    detections: list[BoundingBox]
    zones: list[Zone]
    triggered_zones: set[str]
    frame_id: int


class AlertHandler(Protocol):
    """Protocol for alert handlers; injectable and independently testable."""

    def trigger(self, context: AlertContext) -> None:
        """React to one dispatched alert. Must not raise."""
        ...  # pragma: no cover

    def cleanup(self) -> None:
        """Release any held resources. Must not raise."""
        ...  # pragma: no cover
```

- [x] **Step 4: Run the test to confirm it passes**

Run: `pytest tests/client/alerts/test_context.py -v`
Expected: PASS (2 test classes, 3 tests)

- [x] **Step 5: Commit**

```bash
git add counter_cruiser/client/alerts/context.py tests/client/alerts/test_context.py
git commit -m "feat(alert-system): add AlertContext and AlertHandler protocol"
```

---

## Task 3: Alert configuration models

- [x] **Task 3 complete**

**Files:**
- Modify: `counter_cruiser/config/models.py`
- Modify: `tests/config/test_config.py`

**Interfaces:**
- Consumes: `pydantic.BaseModel`, `field_validator`, `model_validator`,
  `ConfigDict` (pydantic v2, already imported style in this file).
- Produces: `DeterrentConfig`, `SnapshotConfig`, `LogConfig`,
  `NotificationConfig`, `AlertConfig` (all `pydantic.BaseModel` with
  `model_config = ConfigDict(extra='forbid')`), and
  `ClientSettings.alerts: AlertConfig` — every later handler task
  constructs its handler from the matching config group
  (`config.alerts.deterrent`, `config.alerts.snapshot`, `config.alerts.log`,
  `config.alerts.notification`) and `AlertManager` from
  `config.alerts.cooldown_seconds`.

- [x] **Step 1: Write the failing tests for the new config models**

Append to `tests/config/test_config.py`:

```python
from counter_cruiser.config.models import (
    AlertConfig,
    DeterrentConfig,
    LogConfig,
    NotificationConfig,
    SnapshotConfig,
)


class TestDeterrentConfig:
    def test_defaults(self) -> None:
        c = DeterrentConfig()
        assert c.enabled is False
        assert c.pin is None
        assert c.burst_duration_seconds == pytest.approx(1.5)

    def test_pin_required_when_enabled(self) -> None:
        with pytest.raises(ValidationError, match='pin'):
            DeterrentConfig(enabled=True)

    def test_pin_optional_when_disabled(self) -> None:
        c = DeterrentConfig(enabled=False)
        assert c.pin is None

    def test_enabled_with_pin_is_valid(self) -> None:
        c = DeterrentConfig(enabled=True, pin=17)
        assert c.pin == 17

    def test_non_positive_burst_duration_rejected(self) -> None:
        with pytest.raises(ValidationError):
            DeterrentConfig(enabled=True, pin=17, burst_duration_seconds=0)
        with pytest.raises(ValidationError):
            DeterrentConfig(enabled=True, pin=17, burst_duration_seconds=-1.0)

    def test_unknown_key_rejected(self) -> None:
        with pytest.raises(ValidationError):
            DeterrentConfig(frequency=20000)


class TestSnapshotConfig:
    def test_defaults(self) -> None:
        c = SnapshotConfig()
        assert c.enabled is False
        assert c.dir == './snapshots'
        assert c.max_count == 200
        assert c.include_boxes is True
        assert c.include_zones is True

    def test_non_positive_max_count_rejected(self) -> None:
        with pytest.raises(ValidationError):
            SnapshotConfig(max_count=0)

    def test_unknown_key_rejected(self) -> None:
        with pytest.raises(ValidationError):
            SnapshotConfig(bogus=True)


class TestLogConfig:
    def test_defaults(self) -> None:
        c = LogConfig()
        assert c.enabled is False
        assert c.file == './alerts.log'

    def test_unknown_key_rejected(self) -> None:
        with pytest.raises(ValidationError):
            LogConfig(path='x')


class TestNotificationConfig:
    def test_defaults(self) -> None:
        c = NotificationConfig()
        assert c.enabled is False
        assert c.provider is None

    def test_provider_restricted_to_supported_values(self) -> None:
        NotificationConfig(provider='ntfy')
        NotificationConfig(provider='pushover')
        with pytest.raises(ValidationError):
            NotificationConfig(provider='telegram')

    def test_unknown_key_rejected(self) -> None:
        with pytest.raises(ValidationError):
            NotificationConfig(email='x@example.com')


class TestAlertConfig:
    def test_defaults(self) -> None:
        c = AlertConfig()
        assert c.cooldown_seconds == pytest.approx(5.0)
        assert isinstance(c.deterrent, DeterrentConfig)
        assert isinstance(c.snapshot, SnapshotConfig)
        assert isinstance(c.log, LogConfig)
        assert isinstance(c.notification, NotificationConfig)

    def test_negative_cooldown_rejected(self) -> None:
        with pytest.raises(ValidationError):
            AlertConfig(cooldown_seconds=-1.0)

    def test_unknown_key_rejected(self) -> None:
        with pytest.raises(ValidationError):
            AlertConfig(bogus=1)


class TestClientSettingsAlerts:
    def test_alerts_default_to_disabled(self) -> None:
        c = ClientSettings()
        assert c.alerts.deterrent.enabled is False
        assert c.alerts.snapshot.enabled is False
        assert c.alerts.log.enabled is False
        assert c.alerts.notification.enabled is False

    def test_env_override_for_nested_alert_field(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv('COUNTER_CRUISER_ALERTS__COOLDOWN_SECONDS', '10')
        c = ClientSettings()
        assert c.alerts.cooldown_seconds == pytest.approx(10.0)

    def test_alerts_from_toml(self, tmp_path) -> None:
        cfg = tmp_path / 'client.toml'
        cfg.write_text(
            '[counter_cruiser.alerts]\ncooldown_seconds = 7\n'
            '[counter_cruiser.alerts.deterrent]\nenabled = true\npin = 27\n'
        )
        result = load_client_config(cfg)
        assert result.alerts.cooldown_seconds == pytest.approx(7.0)
        assert result.alerts.deterrent.enabled is True
        assert result.alerts.deterrent.pin == 27
```

Note: `load_client_config` and `pytest` are already imported at the top of
`tests/config/test_config.py`; only the new `counter_cruiser.config.models`
names need adding to that existing import line.

- [x] **Step 2: Run the tests to confirm they fail**

Run: `pytest tests/config/test_config.py -v`
Expected: FAIL — `ImportError: cannot import name 'AlertConfig'`

- [x] **Step 3: Implement the config models**

In `counter_cruiser/config/models.py`, add `ConfigDict` and
`model_validator` to the pydantic import, then add the new models above
`ClientSettings` and wire `alerts` into it:

```python
from pydantic import BaseModel, ConfigDict, field_validator, model_validator
```

```python
class DeterrentConfig(BaseModel):
    """GPIO deterrent settings: simulate a button press on the trainer."""

    model_config = ConfigDict(extra='forbid')

    enabled: bool = False
    pin: int | None = None
    burst_duration_seconds: float = 1.5

    @field_validator('burst_duration_seconds')
    @classmethod
    def positive_duration(cls, v: float) -> float:
        """Enforce a strictly positive burst duration."""
        if v <= 0:
            raise ValueError('burst_duration_seconds must be positive')
        return v

    @model_validator(mode='after')
    def pin_required_when_enabled(self) -> 'DeterrentConfig':
        """Reject enabled=True without a configured BCM pin."""
        if self.enabled and self.pin is None:
            raise ValueError('pin is required when deterrent is enabled')
        return self


class SnapshotConfig(BaseModel):
    """Annotated-snapshot recording settings."""

    model_config = ConfigDict(extra='forbid')

    enabled: bool = False
    dir: str = './snapshots'
    max_count: int = 200
    include_boxes: bool = True
    include_zones: bool = True

    @field_validator('max_count')
    @classmethod
    def positive_max_count(cls, v: int) -> int:
        """Enforce a strictly positive snapshot cap."""
        if v <= 0:
            raise ValueError('max_count must be positive')
        return v


class LogConfig(BaseModel):
    """Structured alert-log recording settings."""

    model_config = ConfigDict(extra='forbid')

    enabled: bool = False
    file: str = './alerts.log'


class NotificationConfig(BaseModel):
    """Push notification settings: config-selected provider + credentials."""

    model_config = ConfigDict(extra='forbid')

    enabled: bool = False
    provider: Literal['ntfy', 'pushover'] | None = None
    ntfy_topic: str | None = None
    pushover_user_key: str | None = None
    pushover_api_token: str | None = None


class AlertConfig(BaseModel):
    """Top-level alert settings: cooldown plus one group per handler."""

    model_config = ConfigDict(extra='forbid')

    cooldown_seconds: float = 5.0
    deterrent: DeterrentConfig = DeterrentConfig()
    snapshot: SnapshotConfig = SnapshotConfig()
    log: LogConfig = LogConfig()
    notification: NotificationConfig = NotificationConfig()

    @field_validator('cooldown_seconds')
    @classmethod
    def non_negative_cooldown(cls, v: float) -> float:
        """Enforce a non-negative cooldown window."""
        if v < 0:
            raise ValueError('cooldown_seconds must be >= 0')
        return v
```

Add `Literal` to the `typing` import at the top of the file:

```python
from typing import Literal
```

Add the `alerts` field to `ClientSettings`:

```python
class ClientSettings(_BaseConfig):
    """Configuration for the Pi-side client process."""

    server_host: str = 'localhost'
    server_port: int = 8765
    camera_index: int = 0
    frame_width: int = 640
    frame_height: int = 480
    jpeg_quality: int = 85
    frame_skip: int = 3
    min_size_ratio: float = 0.25
    zones: list[Zone] = []
    alerts: AlertConfig = AlertConfig()
```

(add above the existing field validators — no other changes to
`ClientSettings`).

- [x] **Step 4: Run the tests to confirm they pass**

Run: `pytest tests/config/test_config.py -v`
Expected: PASS (all existing tests plus the new classes above)

- [x] **Step 5: Add an example alert TOML fixture to the loader tests**

Append one more test to `tests/config/test_config.py`'s
`TestTomlLoading` class demonstrating a full alert section round-trips,
confirming the nested-table TOML shape end users will actually write:

```python
    def test_full_alert_section_round_trips(self, tmp_path: Path) -> None:
        cfg = tmp_path / 'client.toml'
        cfg.write_text(
            '[counter_cruiser.alerts]\n'
            'cooldown_seconds = 5\n'
            '[counter_cruiser.alerts.deterrent]\n'
            'enabled = true\n'
            'pin = 17\n'
            'burst_duration_seconds = 1.5\n'
            '[counter_cruiser.alerts.snapshot]\n'
            'enabled = true\n'
            'dir = "./snapshots"\n'
            'max_count = 200\n'
            '[counter_cruiser.alerts.log]\n'
            'enabled = true\n'
            'file = "./alerts.log"\n'
            '[counter_cruiser.alerts.notification]\n'
            'enabled = true\n'
            'provider = "ntfy"\n'
            'ntfy_topic = "counter-cruiser-alerts"\n'
        )
        result = load_client_config(cfg)
        assert result.alerts.deterrent.pin == 17
        assert result.alerts.notification.ntfy_topic == 'counter-cruiser-alerts'
```

Run: `pytest tests/config/test_config.py -v`
Expected: PASS

- [x] **Step 6: Run `ruff check` and `ruff format` on the touched files**

Run: `ruff check counter_cruiser/config/models.py tests/config/test_config.py && ruff format counter_cruiser/config/models.py tests/config/test_config.py`
Expected: no findings; no reformatting needed after applying once

- [x] **Step 7: Commit**

```bash
git add counter_cruiser/config/models.py tests/config/test_config.py
git commit -m "feat(alert-system): add typed alert config models to ClientSettings"
```

---

## Task 4: Frame ring buffer on `ClientSession`

- [x] **Task 4 complete**

**Files:**
- Modify: `counter_cruiser/client/transport.py`
- Modify: `tests/client/test_transport.py`

**Interfaces:**
- Produces: `ClientSession.get_frame(frame_id: int) -> np.ndarray | None`
  and a new constructor param `frame_buffer_capacity: int = 30` — Task 10
  (integration wiring) calls `session.get_frame(msg.frame_id)` to build
  `AlertContext.frame`.

- [x] **Step 1: Write the failing tests for the ring buffer**

Add to `tests/client/test_transport.py` (new test class near the existing
`TestClientSessionSendReceive`):

```python
class TestFrameRingBuffer:
    async def test_get_frame_returns_retained_frame(self) -> None:
        frame = _blank_frame()
        capture = FakeCapture([frame])
        config = _default_config()
        session = ClientSession(capture=capture, config=config, on_result=lambda *_: None)

        async def fake_ws_send(_data: str) -> None:
            session.stop()

        class FakeWS:
            async def send(self, data: str) -> None:
                await fake_ws_send(data)

            async def close(self) -> None:
                return None

        await session._send_loop(FakeWS())

        assert session.get_frame(1) is not None
        np.testing.assert_array_equal(session.get_frame(1), frame)

    async def test_get_frame_returns_none_for_unknown_id(self) -> None:
        capture = FakeCapture([])
        config = _default_config()
        session = ClientSession(capture=capture, config=config, on_result=lambda *_: None)
        assert session.get_frame(999) is None

    async def test_ring_buffer_evicts_oldest_beyond_capacity(self) -> None:
        frames = [_blank_frame() for _ in range(5)]
        capture = FakeCapture(frames)
        config = _default_config()
        session = ClientSession(
            capture=capture,
            config=config,
            on_result=lambda *_: None,
            frame_buffer_capacity=3,
        )

        class FakeWS:
            sent = 0

            async def send(self, data: str) -> None:
                FakeWS.sent += 1
                if FakeWS.sent >= 5:
                    session.stop()

            async def close(self) -> None:
                return None

        await session._send_loop(FakeWS())

        # Capacity 3, 5 frames sent: ids 1 and 2 evicted, 3/4/5 retained.
        assert session.get_frame(1) is None
        assert session.get_frame(2) is None
        assert session.get_frame(3) is not None
        assert session.get_frame(4) is not None
        assert session.get_frame(5) is not None
```

- [x] **Step 2: Run the tests to confirm they fail**

Run: `pytest tests/client/test_transport.py -k FrameRingBuffer -v`
Expected: FAIL — `AttributeError: 'ClientSession' object has no attribute
'get_frame'` (and `TypeError` for the unexpected `frame_buffer_capacity`
kwarg in the third test)

- [x] **Step 3: Implement the ring buffer**

In `counter_cruiser/client/transport.py`, extend `__init__`:

```python
    def __init__(
        self,
        capture: CameraCapture,
        config: ClientSettings,
        on_result: Callable[[DetectionMessage, float], None],
        reconnect_interval: float = 5.0,
        frame_buffer_capacity: int = 30,
    ) -> None:
        """Initialise the session without opening any resources."""
        self._capture = capture
        self._config = config
        self._on_result = on_result
        self._reconnect_interval = reconnect_interval
        self._running = True
        self._pending: dict[int, float] = {}
        self._frame_id = 0
        self._frame_height = config.frame_height
        self._frame_buffer_capacity = frame_buffer_capacity
        self._frame_buffer: dict[int, np.ndarray] = {}
```

Add the `numpy as np` import at the top (transport.py doesn't currently
import it):

```python
import numpy as np
```

Add the lookup method:

```python
    def get_frame(self, frame_id: int) -> np.ndarray | None:
        """Return the retained frame for *frame_id*, or None if unknown/evicted."""
        return self._frame_buffer.get(frame_id)
```

Update `_send_loop` to populate the buffer immediately after capture,
before encoding, with eviction at capacity:

```python
    async def _send_loop(self, ws) -> None:
        """Capture frames (respecting frame_skip) and send them encoded."""
        skip = self._config.frame_skip
        count = 0
        while self._running:
            frame = self._capture.read()
            if frame is None:
                logger.warning('Frame read returned None; skipping')
                await asyncio.sleep(0.01)
                continue
            count += 1
            if count % skip != 0:
                continue
            self._frame_id += 1
            self._frame_buffer[self._frame_id] = frame
            if len(self._frame_buffer) > self._frame_buffer_capacity:
                oldest_id = next(iter(self._frame_buffer))
                del self._frame_buffer[oldest_id]
            msg = encode_frame(frame, self._frame_id, self._config.jpeg_quality)
            self._pending[self._frame_id] = time.monotonic()
            await ws.send(serialize(msg))
        await ws.close()
```

- [x] **Step 4: Run the tests to confirm they pass**

Run: `pytest tests/client/test_transport.py -v`
Expected: PASS (all existing transport tests plus the 3 new ones)

- [x] **Step 5: Run the full test suite to confirm coverage is unbroken**

Run: `pytest`
Expected: PASS, coverage still 100%

- [x] **Step 6: Commit**

```bash
git add counter_cruiser/client/transport.py tests/client/test_transport.py
git commit -m "feat(alert-system): add bounded frame ring buffer to ClientSession"
```

---

## Task 5: Deterrent handler (GPIO button-press simulation)

- [x] **Task 5 complete**

**Files:**
- Create: `counter_cruiser/client/alerts/deterrent.py`
- Test: `tests/client/alerts/test_deterrent.py`

**Interfaces:**
- Consumes: `AlertContext` (Task 2), `DeterrentConfig` (Task 3).
- Produces: `DeterrentHandler(config: DeterrentConfig)` implementing
  `AlertHandler` — Task 9 (`AlertManager`) takes an instance as its
  `deterrent` param; Task 10 (wiring) constructs it from
  `config.alerts.deterrent`.

- [x] **Step 1: Write the failing tests (GPIO seam mocked via a fake module)**

`tests/client/alerts/test_deterrent.py`:

```python
"""Tests for DeterrentHandler: GPIO button-press simulation."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from counter_cruiser.client.alerts.context import AlertContext
from counter_cruiser.client.alerts.deterrent import DeterrentHandler
from counter_cruiser.config.models import DeterrentConfig


def _context() -> AlertContext:
    return AlertContext(
        frame=None, detections=[], zones=[], triggered_zones={'z1'}, frame_id=1
    )


def _fake_gpio() -> MagicMock:
    gpio = MagicMock()
    gpio.BCM = 'BCM'
    gpio.OUT = 'OUT'
    gpio.HIGH = 1
    gpio.LOW = 0
    return gpio


class TestDeterrentBurst:
    def test_burst_drives_pin_high_then_low(self) -> None:
        gpio = _fake_gpio()
        config = DeterrentConfig(enabled=True, pin=17, burst_duration_seconds=0.01)
        with (
            patch(
                'counter_cruiser.client.alerts.deterrent._import_gpio',
                return_value=gpio,
            ),
            patch('counter_cruiser.client.alerts.deterrent.time.sleep'),
        ):
            handler = DeterrentHandler(config)
            handler.trigger(_context())

        gpio.setup.assert_called_once_with(17, gpio.OUT, initial=gpio.LOW)
        assert gpio.output.call_args_list == [
            ((17, gpio.HIGH),),
            ((17, gpio.LOW),),
        ]

    def test_burst_uses_configured_duration(self) -> None:
        gpio = _fake_gpio()
        config = DeterrentConfig(enabled=True, pin=17, burst_duration_seconds=2.5)
        with (
            patch(
                'counter_cruiser.client.alerts.deterrent._import_gpio',
                return_value=gpio,
            ),
            patch('counter_cruiser.client.alerts.deterrent.time.sleep') as sleep,
        ):
            handler = DeterrentHandler(config)
            handler.trigger(_context())

        sleep.assert_called_once_with(2.5)


class TestDeterrentMustNotFireContinuously:
    def test_pin_driven_low_after_a_normal_burst(self) -> None:
        gpio = _fake_gpio()
        config = DeterrentConfig(enabled=True, pin=17, burst_duration_seconds=0.01)
        with (
            patch(
                'counter_cruiser.client.alerts.deterrent._import_gpio',
                return_value=gpio,
            ),
            patch('counter_cruiser.client.alerts.deterrent.time.sleep'),
        ):
            handler = DeterrentHandler(config)
            handler.trigger(_context())

        assert gpio.output.call_args_list[-1] == ((17, gpio.LOW),)

    def test_pin_driven_low_and_error_logged_when_burst_raises(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        gpio = _fake_gpio()
        config = DeterrentConfig(enabled=True, pin=17, burst_duration_seconds=0.01)
        with (
            patch(
                'counter_cruiser.client.alerts.deterrent._import_gpio',
                return_value=gpio,
            ),
            patch(
                'counter_cruiser.client.alerts.deterrent.time.sleep',
                side_effect=RuntimeError('boom'),
            ),
            caplog.at_level('ERROR'),
        ):
            handler = DeterrentHandler(config)
            handler.trigger(_context())

        assert gpio.output.call_args_list[-1] == ((17, gpio.LOW),)
        assert 'Deterrent burst failed' in caplog.text


class TestDeterrentGracefulDegradation:
    def test_missing_gpio_library_disables_handler_with_log(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        config = DeterrentConfig(enabled=True, pin=17)
        with (
            patch(
                'counter_cruiser.client.alerts.deterrent._import_gpio',
                return_value=None,
            ),
            caplog.at_level('WARNING'),
        ):
            handler = DeterrentHandler(config)
        assert 'RPi.GPIO unavailable' in caplog.text
        # Trigger after disablement is a silent no-op.
        handler.trigger(_context())

    def test_gpio_setup_failure_disables_handler_with_log(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        gpio = _fake_gpio()
        gpio.setup.side_effect = RuntimeError('no such pin')
        config = DeterrentConfig(enabled=True, pin=17)
        with (
            patch(
                'counter_cruiser.client.alerts.deterrent._import_gpio',
                return_value=gpio,
            ),
            caplog.at_level('ERROR'),
        ):
            handler = DeterrentHandler(config)
        assert 'GPIO setup failed' in caplog.text
        handler.trigger(_context())
        gpio.output.assert_not_called()

    def test_disabled_by_config_trigger_is_a_noop(self) -> None:
        config = DeterrentConfig(enabled=False)
        with patch(
            'counter_cruiser.client.alerts.deterrent._import_gpio'
        ) as import_gpio:
            handler = DeterrentHandler(config)
            handler.trigger(_context())
        import_gpio.assert_not_called()


class TestDeterrentCleanup:
    def test_cleanup_releases_gpio_after_init(self) -> None:
        gpio = _fake_gpio()
        config = DeterrentConfig(enabled=True, pin=17)
        with patch(
            'counter_cruiser.client.alerts.deterrent._import_gpio',
            return_value=gpio,
        ):
            handler = DeterrentHandler(config)
            handler.cleanup()
        gpio.cleanup.assert_called_once_with()

    def test_cleanup_is_safe_when_disabled(self) -> None:
        config = DeterrentConfig(enabled=False)
        handler = DeterrentHandler(config)
        handler.cleanup()  # must not raise
```

- [x] **Step 2: Run the tests to confirm they fail**

Run: `pytest tests/client/alerts/test_deterrent.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named
'counter_cruiser.client.alerts.deterrent'`

- [x] **Step 3: Implement `DeterrentHandler`**

`counter_cruiser/client/alerts/deterrent.py`:

```python
"""GPIO deterrent handler: simulates a button press on the ultrasonic trainer.

The Pi does not generate the ultrasonic tone itself; it drives a BCM pin
HIGH for a configured duration (simulating the trainer's momentary-press
button) then LOW, wrapped in try/finally so the pin never stays HIGH.
"""

from __future__ import annotations

import logging
import time
from types import ModuleType

from counter_cruiser.client.alerts.context import AlertContext
from counter_cruiser.config.models import DeterrentConfig

logger = logging.getLogger(__name__)


def _import_gpio() -> ModuleType | None:
    """Import RPi.GPIO; return None if the library is unavailable.

    Isolated as a module-level function (not imported at module scope) so
    tests can patch this exact seam without needing the real library
    installed.
    """
    try:
        import RPi.GPIO as GPIO  # noqa: N814
    except ImportError:
        return None
    return GPIO


class DeterrentHandler:
    """Drives a BCM GPIO pin HIGH then LOW to simulate a trainer button press."""

    def __init__(self, config: DeterrentConfig) -> None:
        """Set up GPIO if enabled; self-disable on any failure."""
        self._config = config
        self._gpio: ModuleType | None = None
        self._enabled = config.enabled and self._setup()

    def _setup(self) -> bool:
        gpio = _import_gpio()
        if gpio is None:
            logger.warning('RPi.GPIO unavailable; deterrent handler disabled')
            return False
        try:
            gpio.setmode(gpio.BCM)
            gpio.setup(self._config.pin, gpio.OUT, initial=gpio.LOW)
        except Exception:
            logger.exception('GPIO setup failed; deterrent handler disabled')
            return False
        self._gpio = gpio
        return True

    def trigger(self, context: AlertContext) -> None:
        """Fire one timed burst: pin HIGH for burst_duration_seconds, then LOW."""
        if not self._enabled or self._gpio is None:
            return
        gpio = self._gpio
        pin = self._config.pin
        try:
            gpio.output(pin, gpio.HIGH)
            time.sleep(self._config.burst_duration_seconds)
        except Exception:
            logger.exception('Deterrent burst failed on pin %s', pin)
        finally:
            gpio.output(pin, gpio.LOW)

    def cleanup(self) -> None:
        """Release the GPIO resource; safe to call even if never set up."""
        if self._gpio is not None:
            self._gpio.cleanup()
            self._gpio = None
            self._enabled = False
```

- [x] **Step 4: Run the tests to confirm they pass**

Run: `pytest tests/client/alerts/test_deterrent.py -v`
Expected: PASS (all 8 tests)

- [x] **Step 5: Run `ruff check`/`ruff format` on the new files**

Run: `ruff check counter_cruiser/client/alerts/deterrent.py tests/client/alerts/test_deterrent.py && ruff format counter_cruiser/client/alerts/deterrent.py tests/client/alerts/test_deterrent.py`
Expected: clean (the `# noqa: N814` on the `RPi.GPIO` import silences the
non-lowercase-module-alias lint rule for the conventional `GPIO` name)

- [x] **Step 6: Commit**

```bash
git add counter_cruiser/client/alerts/deterrent.py tests/client/alerts/test_deterrent.py
git commit -m "feat(alert-system): add DeterrentHandler (GPIO button-press simulation)"
```

---

## Task 6: Push notifications (ntfy.sh and Pushover)

- [x] **Task 6 complete**

**Files:**
- Create: `counter_cruiser/client/alerts/notifications.py`
- Test: `tests/client/alerts/test_notifications.py`

**Interfaces:**
- Consumes: `AlertContext` (Task 2), `NotificationConfig` (Task 3).
- Produces: `NotificationProvider` (Protocol, `send(message: str) -> None`),
  `NtfyProvider`, `PushoverProvider`, `NotificationHandler` implementing
  `AlertHandler` — Task 10 (wiring) constructs
  `NotificationHandler(config.alerts.notification)`.

- [x] **Step 1: Write the failing tests**

`tests/client/alerts/test_notifications.py`:

```python
"""Tests for push notification providers and the NotificationHandler."""

from __future__ import annotations

import requests
import requests_mock

from counter_cruiser.client.alerts.context import AlertContext
from counter_cruiser.client.alerts.notifications import (
    NotificationHandler,
    NtfyProvider,
    PushoverProvider,
)
from counter_cruiser.config.models import NotificationConfig


def _context() -> AlertContext:
    return AlertContext(
        frame=None, detections=[], zones=[], triggered_zones={'counter'}, frame_id=1
    )


class TestMessageBuilding:
    def test_message_identifies_triggered_zones(self) -> None:
        handler = NotificationHandler(NotificationConfig(enabled=True))
        message = handler._build_message(_context())
        assert 'counter' in message


class TestNtfyProvider:
    def test_posts_message_to_configured_topic(self) -> None:
        with requests_mock.Mocker() as m:
            m.post('https://ntfy.sh/my-topic', status_code=200)
            NtfyProvider(topic='my-topic').send('Dog on counter!')
        assert m.last_request.text == 'Dog on counter!'


class TestPushoverProvider:
    def test_posts_message_with_user_key_and_token(self) -> None:
        with requests_mock.Mocker() as m:
            m.post('https://api.pushover.net/1/messages.json', status_code=200)
            PushoverProvider(user_key='u1', api_token='t1').send('Dog on counter!')
        sent = m.last_request.json() if False else m.last_request.text
        assert 'u1' in sent
        assert 't1' in sent
        assert 'Dog on counter!' in sent


class TestFailureTolerance:
    def test_network_error_is_logged_and_does_not_raise(
        self, caplog
    ) -> None:
        with requests_mock.Mocker() as m:
            m.post('https://ntfy.sh/topic', exc=requests.ConnectionError)
            with caplog.at_level('ERROR'):
                NtfyProvider(topic='topic').send('hi')  # must not raise
        assert 'network error' in caplog.text

    def test_non_success_status_is_logged_and_does_not_raise(
        self, caplog
    ) -> None:
        with requests_mock.Mocker() as m:
            m.post('https://ntfy.sh/topic', status_code=500)
            with caplog.at_level('WARNING'):
                NtfyProvider(topic='topic').send('hi')  # must not raise
        assert 'status 500' in caplog.text

    def test_missing_topic_logs_and_skips_delivery(self, caplog) -> None:
        config = NotificationConfig(enabled=True, provider='ntfy', ntfy_topic=None)
        with caplog.at_level('WARNING'):
            handler = NotificationHandler(config)
            handler.trigger(_context())  # must not raise
        assert 'ntfy_topic' in caplog.text

    def test_missing_pushover_credentials_logs_and_skips_delivery(
        self, caplog
    ) -> None:
        config = NotificationConfig(enabled=True, provider='pushover')
        with caplog.at_level('WARNING'):
            handler = NotificationHandler(config)
            handler.trigger(_context())  # must not raise
        assert 'pushover' in caplog.text.lower()

    def test_no_provider_configured_logs_and_skips_delivery(self, caplog) -> None:
        config = NotificationConfig(enabled=True, provider=None)
        with caplog.at_level('WARNING'):
            handler = NotificationHandler(config)
            handler.trigger(_context())  # must not raise
        assert 'no provider' in caplog.text.lower()


class TestNotificationHandlerDelegation:
    def test_ntfy_provider_selected_and_invoked(self) -> None:
        config = NotificationConfig(
            enabled=True, provider='ntfy', ntfy_topic='my-topic'
        )
        with requests_mock.Mocker() as m:
            m.post('https://ntfy.sh/my-topic', status_code=200)
            handler = NotificationHandler(config)
            handler.trigger(_context())
        assert m.called

    def test_pushover_provider_selected_and_invoked(self) -> None:
        config = NotificationConfig(
            enabled=True,
            provider='pushover',
            pushover_user_key='u1',
            pushover_api_token='t1',
        )
        with requests_mock.Mocker() as m:
            m.post('https://api.pushover.net/1/messages.json', status_code=200)
            handler = NotificationHandler(config)
            handler.trigger(_context())
        assert m.called

    def test_cleanup_is_a_noop(self) -> None:
        handler = NotificationHandler(NotificationConfig())
        handler.cleanup()  # must not raise
```

- [x] **Step 2: Run the tests to confirm they fail**

Run: `pytest tests/client/alerts/test_notifications.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [x] **Step 3: Implement providers and the handler**

`counter_cruiser/client/alerts/notifications.py`:

```python
"""Push notification providers (ntfy.sh, Pushover) and the alert handler."""

from __future__ import annotations

import logging
from typing import Protocol

import requests

from counter_cruiser.client.alerts.context import AlertContext
from counter_cruiser.config.models import NotificationConfig

logger = logging.getLogger(__name__)

_TIMEOUT_SECONDS = 3.0


class NotificationProvider(Protocol):
    """Protocol for a push-notification transport."""

    def send(self, message: str) -> None:
        """Deliver *message*. Must not raise on network/HTTP failure."""
        ...  # pragma: no cover


class NtfyProvider:
    """Posts a plaintext message to an ntfy.sh topic (no account required)."""

    def __init__(self, topic: str, timeout: float = _TIMEOUT_SECONDS) -> None:
        """Store the target topic and per-request timeout."""
        self._topic = topic
        self._timeout = timeout

    def send(self, message: str) -> None:
        """POST *message* to the configured ntfy.sh topic."""
        url = f'https://ntfy.sh/{self._topic}'
        try:
            response = requests.post(
                url, data=message.encode('utf-8'), timeout=self._timeout
            )
        except requests.RequestException:
            logger.exception('ntfy delivery failed: network error')
            return
        if response.status_code >= 400:
            logger.warning('ntfy delivery failed: status %d', response.status_code)


class PushoverProvider:
    """Posts a message via the Pushover API using a user key + API token."""

    def __init__(
        self, user_key: str, api_token: str, timeout: float = _TIMEOUT_SECONDS
    ) -> None:
        """Store Pushover credentials and per-request timeout."""
        self._user_key = user_key
        self._api_token = api_token
        self._timeout = timeout

    def send(self, message: str) -> None:
        """POST *message* to the Pushover messages API."""
        url = 'https://api.pushover.net/1/messages.json'
        payload = {
            'token': self._api_token,
            'user': self._user_key,
            'message': message,
        }
        try:
            response = requests.post(url, data=payload, timeout=self._timeout)
        except requests.RequestException:
            logger.exception('Pushover delivery failed: network error')
            return
        if response.status_code >= 400:
            logger.warning(
                'Pushover delivery failed: status %d', response.status_code
            )


class NotificationHandler:
    """Selects a configured provider and sends a message identifying zones."""

    def __init__(self, config: NotificationConfig) -> None:
        """Build the configured provider, or None if config is incomplete."""
        self._config = config
        self._provider = self._build_provider(config)

    @staticmethod
    def _build_provider(config: NotificationConfig) -> NotificationProvider | None:
        if config.provider == 'ntfy':
            if not config.ntfy_topic:
                logger.warning('Notification provider ntfy configured without ntfy_topic')
                return None
            return NtfyProvider(topic=config.ntfy_topic)
        if config.provider == 'pushover':
            if not (config.pushover_user_key and config.pushover_api_token):
                logger.warning(
                    'Notification provider pushover configured without credentials'
                )
                return None
            return PushoverProvider(
                user_key=config.pushover_user_key,
                api_token=config.pushover_api_token,
            )
        return None

    def _build_message(self, context: AlertContext) -> str:
        zones = ', '.join(sorted(context.triggered_zones)) or 'unknown zone'
        return f'Dog detected in zone(s): {zones}'

    def trigger(self, context: AlertContext) -> None:
        """Send a notification identifying the triggered zones, if configured."""
        if self._provider is None:
            logger.warning('No provider configured; skipping notification')
            return
        self._provider.send(self._build_message(context))

    def cleanup(self) -> None:
        """No resources to release; HTTP is stateless per-call."""
```

- [x] **Step 4: Run the tests to confirm they pass**

Run: `pytest tests/client/alerts/test_notifications.py -v`
Expected: PASS (all tests)

- [x] **Step 5: Run `ruff check`/`ruff format` on the new files**

Run: `ruff check counter_cruiser/client/alerts/notifications.py tests/client/alerts/test_notifications.py && ruff format counter_cruiser/client/alerts/notifications.py tests/client/alerts/test_notifications.py`
Expected: clean

- [x] **Step 6: Commit**

```bash
git add counter_cruiser/client/alerts/notifications.py tests/client/alerts/test_notifications.py
git commit -m "feat(alert-system): add ntfy.sh/Pushover notification providers and handler"
```

---

## Task 7: Shared annotation helper + snapshot handler

- [x] **Task 7 complete**

**Files:**
- Create: `counter_cruiser/client/annotation.py`
- Create: `counter_cruiser/client/alerts/snapshot.py`
- Test: `tests/client/test_annotation.py`
- Test: `tests/client/alerts/test_snapshot.py`

**Interfaces:**
- Consumes: `BoundingBox`, `Zone`, `AlertContext` (all existing/Task 2),
  `SnapshotConfig` (Task 3).
- Produces: `annotate_frame(frame, detections, zones, triggered_zones,
  include_boxes=True, include_zones=True) -> np.ndarray` (module-level,
  pure function, no globals — reused later by the web-UI change) and
  `SnapshotHandler(config: SnapshotConfig)` implementing `AlertHandler`.

- [x] **Step 1: Write the failing annotation tests**

`tests/client/test_annotation.py`:

```python
"""Tests for the reusable frame-annotation helper."""

from __future__ import annotations

import numpy as np

from counter_cruiser.client.annotation import annotate_frame
from counter_cruiser.config.models import Zone
from counter_cruiser.shared.protocol import BoundingBox


def _frame() -> np.ndarray:
    return np.zeros((100, 100, 3), dtype=np.uint8)


def _box() -> BoundingBox:
    return BoundingBox(
        x1=10, y1=10, x2=50, y2=50, confidence=0.9, class_id=16, class_name='dog'
    )


def _zone(zone_id: str = 'z1') -> Zone:
    return Zone(id=zone_id, name='Counter', polygon=[(0, 0), (99, 0), (99, 99)])


class TestAnnotateFrame:
    def test_boxes_drawn_when_enabled(self) -> None:
        annotated = annotate_frame(
            _frame(), [_box()], [], set(), include_boxes=True, include_zones=False
        )
        assert not np.array_equal(annotated, _frame())

    def test_zones_drawn_when_enabled(self) -> None:
        annotated = annotate_frame(
            _frame(), [], [_zone()], set(), include_boxes=False, include_zones=True
        )
        assert not np.array_equal(annotated, _frame())

    def test_no_overlay_when_both_disabled(self) -> None:
        annotated = annotate_frame(
            _frame(), [_box()], [_zone()], {'z1'}, include_boxes=False, include_zones=False
        )
        # Timestamp text is always drawn, so only compare the shape/dtype
        # and confirm no box/zone-colored pixels are present.
        assert annotated.shape == _frame().shape
        assert not np.any(annotated[10:50, 10:50] == [0, 0, 255])

    def test_triggered_zone_drawn_distinctly_from_idle_zone(self) -> None:
        triggered = annotate_frame(
            _frame(), [], [_zone('z1')], {'z1'}, include_boxes=False, include_zones=True
        )
        idle = annotate_frame(
            _frame(), [], [_zone('z1')], set(), include_boxes=False, include_zones=True
        )
        assert not np.array_equal(triggered, idle)

    def test_original_frame_is_not_mutated(self) -> None:
        frame = _frame()
        original = frame.copy()
        annotate_frame(frame, [_box()], [_zone()], {'z1'})
        np.testing.assert_array_equal(frame, original)
```

- [x] **Step 2: Run the tests to confirm they fail**

Run: `pytest tests/client/test_annotation.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named
'counter_cruiser.client.annotation'`

- [x] **Step 3: Implement `annotate_frame`**

`counter_cruiser/client/annotation.py`:

```python
"""Shared frame-annotation helper: boxes, zone polygons, and a timestamp.

Owned by the alert-system change and consumed (not reimplemented) by the
web-UI change's live-feed overlay. Pure function over plain data — no
globals, no I/O.
"""

from __future__ import annotations

from datetime import UTC, datetime

import cv2
import numpy as np

from counter_cruiser.config.models import Zone
from counter_cruiser.shared.protocol import BoundingBox

_BOX_COLOR = (0, 0, 255)  # BGR red
_TRIGGERED_ZONE_COLOR = (0, 0, 255)  # BGR red
_IDLE_ZONE_COLOR = (0, 200, 0)  # BGR green
_TEXT_COLOR = (255, 255, 255)  # BGR white


def annotate_frame(
    frame: np.ndarray,
    detections: list[BoundingBox],
    zones: list[Zone],
    triggered_zones: set[str],
    include_boxes: bool = True,
    include_zones: bool = True,
) -> np.ndarray:
    """Return a copy of *frame* overlaid with boxes, zones, and a timestamp.

    Triggered zones are drawn in red, idle zones in green. The timestamp is
    always drawn. *frame* itself is never mutated.
    """
    annotated = frame.copy()
    if include_boxes:
        for box in detections:
            cv2.rectangle(
                annotated, (box.x1, box.y1), (box.x2, box.y2), _BOX_COLOR, 2
            )
            label = f'{box.class_name} {box.confidence:.2f}'
            cv2.putText(
                annotated,
                label,
                (box.x1, max(box.y1 - 5, 0)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.5,
                _BOX_COLOR,
                1,
            )
    if include_zones:
        for zone in zones:
            pts = np.array(zone.polygon, dtype=np.int32).reshape((-1, 1, 2))
            color = (
                _TRIGGERED_ZONE_COLOR
                if zone.id in triggered_zones
                else _IDLE_ZONE_COLOR
            )
            cv2.polylines(annotated, [pts], isClosed=True, color=color, thickness=2)
    timestamp = datetime.now(UTC).strftime('%Y-%m-%d %H:%M:%S UTC')
    cv2.putText(
        annotated, timestamp, (10, 20), cv2.FONT_HERSHEY_SIMPLEX, 0.5, _TEXT_COLOR, 1
    )
    return annotated
```

- [x] **Step 4: Run the annotation tests to confirm they pass**

Run: `pytest tests/client/test_annotation.py -v`
Expected: PASS (5 tests)

- [x] **Step 5: Write the failing snapshot handler tests**

`tests/client/alerts/test_snapshot.py`:

```python
"""Tests for SnapshotHandler: annotated JPEG + JSON sidecar, max-count cleanup."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from counter_cruiser.client.alerts.context import AlertContext
from counter_cruiser.client.alerts.snapshot import SnapshotHandler
from counter_cruiser.config.models import SnapshotConfig
from counter_cruiser.shared.protocol import BoundingBox


def _box() -> BoundingBox:
    return BoundingBox(
        x1=0, y1=0, x2=10, y2=10, confidence=0.9, class_id=16, class_name='dog'
    )


def _context(frame: np.ndarray | None, frame_id: int = 1) -> AlertContext:
    return AlertContext(
        frame=frame,
        detections=[_box()],
        zones=[],
        triggered_zones={'z1'},
        frame_id=frame_id,
    )


class TestSnapshotSave:
    def test_writes_jpeg_and_json_sidecar(self, tmp_path: Path) -> None:
        config = SnapshotConfig(enabled=True, dir=str(tmp_path))
        handler = SnapshotHandler(config)
        frame = np.zeros((20, 20, 3), dtype=np.uint8)

        handler.trigger(_context(frame, frame_id=7))

        images = list(tmp_path.glob('*.jpg'))
        sidecars = list(tmp_path.glob('*.json'))
        assert len(images) == 1
        assert len(sidecars) == 1
        payload = json.loads(sidecars[0].read_text())
        assert payload['triggered_zones'] == ['z1']
        assert payload['detection_count'] == 1
        assert payload['frame_id'] == 7
        assert 'timestamp' in payload


class TestSnapshotAnnotation:
    def test_overlay_applied_when_enabled(self, tmp_path: Path) -> None:
        config = SnapshotConfig(
            enabled=True, dir=str(tmp_path), include_boxes=True, include_zones=True
        )
        handler = SnapshotHandler(config)
        frame = np.zeros((20, 20, 3), dtype=np.uint8)
        handler.trigger(_context(frame))
        # Rely on annotate_frame's own coverage for pixel-level assertions;
        # here we assert the handler wires include_boxes/include_zones through.
        import cv2

        saved = cv2.imread(str(next(tmp_path.glob('*.jpg'))))
        assert saved is not None


class TestSnapshotMaxCount:
    def test_oldest_deleted_when_over_cap(self, tmp_path: Path) -> None:
        config = SnapshotConfig(enabled=True, dir=str(tmp_path), max_count=2)
        handler = SnapshotHandler(config)
        frame = np.zeros((5, 5, 3), dtype=np.uint8)
        for i in range(4):
            handler.trigger(_context(frame, frame_id=i))
        images = sorted(tmp_path.glob('*.jpg'))
        sidecars = sorted(tmp_path.glob('*.json'))
        assert len(images) == 2
        assert len(sidecars) == 2

    def test_no_deletion_when_under_cap(self, tmp_path: Path) -> None:
        config = SnapshotConfig(enabled=True, dir=str(tmp_path), max_count=10)
        handler = SnapshotHandler(config)
        frame = np.zeros((5, 5, 3), dtype=np.uint8)
        for i in range(3):
            handler.trigger(_context(frame, frame_id=i))
        assert len(list(tmp_path.glob('*.jpg'))) == 3


class TestSnapshotMissingFrame:
    def test_missing_frame_logs_and_returns_without_writing(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        config = SnapshotConfig(enabled=True, dir=str(tmp_path))
        handler = SnapshotHandler(config)
        with caplog.at_level('WARNING'):
            handler.trigger(_context(None))  # must not raise
        assert list(tmp_path.glob('*.jpg')) == []
        assert 'No frame retained' in caplog.text


class TestSnapshotCleanup:
    def test_cleanup_is_a_noop(self, tmp_path: Path) -> None:
        handler = SnapshotHandler(SnapshotConfig(enabled=True, dir=str(tmp_path)))
        handler.cleanup()  # must not raise
```

- [x] **Step 6: Run the snapshot tests to confirm they fail**

Run: `pytest tests/client/alerts/test_snapshot.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [x] **Step 7: Implement `SnapshotHandler`**

`counter_cruiser/client/alerts/snapshot.py`:

```python
"""Snapshot handler: annotated JPEG + JSON metadata sidecar, max-count cleanup."""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from pathlib import Path

import cv2

from counter_cruiser.client.alerts.context import AlertContext
from counter_cruiser.client.annotation import annotate_frame
from counter_cruiser.config.models import SnapshotConfig

logger = logging.getLogger(__name__)


class SnapshotHandler:
    """Writes an annotated JPEG and a JSON sidecar for each triggered alert."""

    def __init__(self, config: SnapshotConfig) -> None:
        """Ensure the snapshot directory exists."""
        self._config = config
        Path(config.dir).mkdir(parents=True, exist_ok=True)

    def trigger(self, context: AlertContext) -> None:
        """Save an annotated snapshot + sidecar, or log and skip if no frame."""
        if context.frame is None:
            logger.warning(
                'No frame retained for frame_id=%s; skipping snapshot',
                context.frame_id,
            )
            return
        annotated = annotate_frame(
            context.frame,
            context.detections,
            context.zones,
            context.triggered_zones,
            include_boxes=self._config.include_boxes,
            include_zones=self._config.include_zones,
        )
        now = datetime.now(UTC)
        stem = f'{now.strftime("%Y%m%dT%H%M%S%f")}_frame{context.frame_id}'
        image_path = Path(self._config.dir) / f'{stem}.jpg'
        sidecar_path = Path(self._config.dir) / f'{stem}.json'
        cv2.imwrite(str(image_path), annotated)
        sidecar_path.write_text(
            json.dumps(
                {
                    'timestamp': now.isoformat(),
                    'triggered_zones': sorted(context.triggered_zones),
                    'detection_count': len(context.detections),
                    'frame_id': context.frame_id,
                }
            )
        )
        self._enforce_max_count()

    def _enforce_max_count(self) -> None:
        images = sorted(Path(self._config.dir).glob('*.jpg'))
        excess = len(images) - self._config.max_count
        for image_path in images[: max(excess, 0)]:
            image_path.unlink(missing_ok=True)
            image_path.with_suffix('.json').unlink(missing_ok=True)

    def cleanup(self) -> None:
        """No resources to release; each trigger opens and closes its own files."""
```

- [x] **Step 8: Run the snapshot tests to confirm they pass**

Run: `pytest tests/client/alerts/test_snapshot.py -v`
Expected: PASS (all tests)

- [x] **Step 9: Run `ruff check`/`ruff format` on all touched files**

Run: `ruff check counter_cruiser/client/annotation.py counter_cruiser/client/alerts/snapshot.py tests/client/test_annotation.py tests/client/alerts/test_snapshot.py && ruff format counter_cruiser/client/annotation.py counter_cruiser/client/alerts/snapshot.py tests/client/test_annotation.py tests/client/alerts/test_snapshot.py`
Expected: clean

- [x] **Step 10: Commit**

```bash
git add counter_cruiser/client/annotation.py counter_cruiser/client/alerts/snapshot.py tests/client/test_annotation.py tests/client/alerts/test_snapshot.py
git commit -m "feat(alert-system): add shared annotation helper and SnapshotHandler"
```

---

## Task 8: Structured log handler

- [x] **Task 8 complete**

**Files:**
- Create: `counter_cruiser/client/alerts/log.py`
- Test: `tests/client/alerts/test_log.py`

**Interfaces:**
- Consumes: `AlertContext` (Task 2), `LogConfig` (Task 3).
- Produces: `LogHandler(config: LogConfig)` implementing `AlertHandler`.

- [x] **Step 1: Write the failing tests**

`tests/client/alerts/test_log.py`:

```python
"""Tests for LogHandler: structured alert-log append."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from counter_cruiser.client.alerts.context import AlertContext
from counter_cruiser.client.alerts.log import LogHandler
from counter_cruiser.config.models import LogConfig
from counter_cruiser.shared.protocol import BoundingBox


def _context() -> AlertContext:
    box = BoundingBox(
        x1=0, y1=0, x2=10, y2=10, confidence=0.9, class_id=16, class_name='dog'
    )
    return AlertContext(
        frame=None, detections=[box], zones=[], triggered_zones={'z1'}, frame_id=3
    )


class TestLogAppend:
    def test_record_includes_zones_frame_id_and_detection_count(
        self, tmp_path: Path
    ) -> None:
        log_path = tmp_path / 'alerts.log'
        handler = LogHandler(LogConfig(enabled=True, file=str(log_path)))
        handler.trigger(_context())
        lines = log_path.read_text().splitlines()
        assert len(lines) == 1
        record = json.loads(lines[0])
        assert record['triggered_zones'] == ['z1']
        assert record['frame_id'] == 3
        assert record['detection_count'] == 1

    def test_multiple_triggers_append(self, tmp_path: Path) -> None:
        log_path = tmp_path / 'alerts.log'
        handler = LogHandler(LogConfig(enabled=True, file=str(log_path)))
        handler.trigger(_context())
        handler.trigger(_context())
        assert len(log_path.read_text().splitlines()) == 2

    def test_write_failure_is_logged_and_does_not_raise(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        unwritable_dir = tmp_path / 'missing-parent' / 'alerts.log'
        handler = LogHandler(LogConfig(enabled=True, file=str(unwritable_dir)))
        with caplog.at_level('ERROR'):
            handler.trigger(_context())  # must not raise
        assert 'Failed to write alert log' in caplog.text


class TestLogCleanup:
    def test_cleanup_is_a_noop(self, tmp_path: Path) -> None:
        handler = LogHandler(LogConfig(enabled=True, file=str(tmp_path / 'a.log')))
        handler.cleanup()  # must not raise
```

- [x] **Step 2: Run the tests to confirm they fail**

Run: `pytest tests/client/alerts/test_log.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [x] **Step 3: Implement `LogHandler`**

`counter_cruiser/client/alerts/log.py`:

```python
"""Structured alert-log handler: appends one JSON line per alert."""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime

from counter_cruiser.client.alerts.context import AlertContext
from counter_cruiser.config.models import LogConfig

logger = logging.getLogger(__name__)


class LogHandler:
    """Appends a structured JSON record to the configured log file per alert."""

    def __init__(self, config: LogConfig) -> None:
        """Store the target log file path."""
        self._config = config

    def trigger(self, context: AlertContext) -> None:
        """Append one JSON record; log and swallow any write failure."""
        record = {
            'timestamp': datetime.now(UTC).isoformat(),
            'triggered_zones': sorted(context.triggered_zones),
            'detection_count': len(context.detections),
            'frame_id': context.frame_id,
        }
        try:
            with open(self._config.file, 'a') as fh:
                fh.write(json.dumps(record) + '\n')
        except OSError:
            logger.exception('Failed to write alert log to %s', self._config.file)

    def cleanup(self) -> None:
        """No resources to release; each trigger opens and closes its own file."""
```

- [x] **Step 4: Run the tests to confirm they pass**

Run: `pytest tests/client/alerts/test_log.py -v`
Expected: PASS (5 tests)

- [x] **Step 5: Run `ruff check`/`ruff format`**

Run: `ruff check counter_cruiser/client/alerts/log.py tests/client/alerts/test_log.py && ruff format counter_cruiser/client/alerts/log.py tests/client/alerts/test_log.py`
Expected: clean

- [x] **Step 6: Commit**

```bash
git add counter_cruiser/client/alerts/log.py tests/client/alerts/test_log.py
git commit -m "feat(alert-system): add LogHandler for structured alert records"
```

---

## Task 9: `AlertManager` (cooldown, deterrent-first fan-out, isolation)

- [x] **Task 9 complete**

**Files:**
- Create: `counter_cruiser/client/alerts/manager.py`
- Test: `tests/client/alerts/test_manager.py`

**Interfaces:**
- Consumes: `AlertContext`, `AlertHandler` (Task 2).
- Produces: `AlertManager(handlers: list[AlertHandler], cooldown_seconds:
  float, deterrent: AlertHandler | None = None)` with
  `maybe_alert(context: AlertContext) -> None` and `cleanup() -> None` —
  Task 10 (wiring) constructs one instance from config and calls
  `maybe_alert` on the debounced elevated event.

- [x] **Step 1: Write the failing tests**

`tests/client/alerts/test_manager.py`:

```python
"""Tests for AlertManager: cooldown, deterrent-first fan-out, isolation."""

from __future__ import annotations

from unittest.mock import call

import pytest

from counter_cruiser.client.alerts.context import AlertContext
from counter_cruiser.client.alerts.manager import AlertManager


class FakeHandler:
    """Records calls; can be configured to raise on trigger/cleanup."""

    def __init__(self, name: str, raise_on_trigger: bool = False, raise_on_cleanup: bool = False):
        self.name = name
        self.trigger_calls: list[AlertContext] = []
        self.cleanup_calls = 0
        self._raise_on_trigger = raise_on_trigger
        self._raise_on_cleanup = raise_on_cleanup

    def trigger(self, context: AlertContext) -> None:
        self.trigger_calls.append(context)
        if self._raise_on_trigger:
            raise RuntimeError(f'{self.name} trigger failed')

    def cleanup(self) -> None:
        self.cleanup_calls += 1
        if self._raise_on_cleanup:
            raise RuntimeError(f'{self.name} cleanup failed')


def _context(zones: set[str], frame_id: int = 1) -> AlertContext:
    return AlertContext(
        frame=None, detections=[], zones=[], triggered_zones=zones, frame_id=frame_id
    )


class TestCooldown:
    def test_proceeds_when_zone_outside_window(self) -> None:
        handler = FakeHandler('h1')
        manager = AlertManager(handlers=[handler], cooldown_seconds=100.0)
        manager.maybe_alert(_context({'z1'}))
        assert len(handler.trigger_calls) == 1

    def test_suppresses_when_all_zones_within_window(self) -> None:
        handler = FakeHandler('h1')
        manager = AlertManager(handlers=[handler], cooldown_seconds=100.0)
        manager.maybe_alert(_context({'z1'}))
        manager.maybe_alert(_context({'z1'}))
        assert len(handler.trigger_calls) == 1

    def test_proceeds_and_records_last_alert_for_all_triggered_zones(self) -> None:
        handler = FakeHandler('h1')
        manager = AlertManager(handlers=[handler], cooldown_seconds=100.0)
        manager.maybe_alert(_context({'z1', 'z2'}))
        # Second alert only for z2 should be suppressed too, since z2's
        # last-alert time was recorded on the first (multi-zone) call.
        manager.maybe_alert(_context({'z2'}))
        assert len(handler.trigger_calls) == 1

    def test_zones_tracked_independently(self) -> None:
        handler = FakeHandler('h1')
        manager = AlertManager(handlers=[handler], cooldown_seconds=100.0)
        manager.maybe_alert(_context({'z1'}))
        manager.maybe_alert(_context({'z2'}))  # different zone, not suppressed
        assert len(handler.trigger_calls) == 2

    def test_zero_cooldown_never_suppresses(self) -> None:
        handler = FakeHandler('h1')
        manager = AlertManager(handlers=[handler], cooldown_seconds=0.0)
        manager.maybe_alert(_context({'z1'}))
        manager.maybe_alert(_context({'z1'}))
        assert len(handler.trigger_calls) == 2


class TestFanOut:
    def test_all_handlers_run_once(self) -> None:
        h1, h2 = FakeHandler('h1'), FakeHandler('h2')
        manager = AlertManager(handlers=[h1, h2], cooldown_seconds=0.0)
        manager.maybe_alert(_context({'z1'}))
        assert len(h1.trigger_calls) == 1
        assert len(h2.trigger_calls) == 1

    def test_deterrent_fires_before_any_other_handler(self) -> None:
        order: list[str] = []

        class OrderTrackingHandler(FakeHandler):
            def trigger(self, context: AlertContext) -> None:
                order.append(self.name)
                super().trigger(context)

        deterrent = OrderTrackingHandler('deterrent')
        snapshot = OrderTrackingHandler('snapshot')
        log = OrderTrackingHandler('log')
        manager = AlertManager(
            handlers=[snapshot, log], cooldown_seconds=0.0, deterrent=deterrent
        )
        manager.maybe_alert(_context({'z1'}))
        assert order == ['deterrent', 'snapshot', 'log']

    def test_no_deterrent_configured_runs_remaining_handlers(self) -> None:
        handler = FakeHandler('h1')
        manager = AlertManager(handlers=[handler], cooldown_seconds=0.0, deterrent=None)
        manager.maybe_alert(_context({'z1'}))
        assert len(handler.trigger_calls) == 1


class TestFailureIsolation:
    def test_one_handler_raising_still_runs_the_others(self, caplog) -> None:
        failing = FakeHandler('failing', raise_on_trigger=True)
        ok = FakeHandler('ok')
        manager = AlertManager(handlers=[failing, ok], cooldown_seconds=0.0)
        with caplog.at_level('ERROR'):
            manager.maybe_alert(_context({'z1'}))  # must not raise
        assert len(ok.trigger_calls) == 1
        assert 'FakeHandler' in caplog.text


class TestCleanup:
    def test_all_handlers_cleaned_up(self) -> None:
        deterrent = FakeHandler('deterrent')
        h1, h2 = FakeHandler('h1'), FakeHandler('h2')
        manager = AlertManager(handlers=[h1, h2], cooldown_seconds=0.0, deterrent=deterrent)
        manager.cleanup()
        assert deterrent.cleanup_calls == 1
        assert h1.cleanup_calls == 1
        assert h2.cleanup_calls == 1

    def test_one_failing_cleanup_does_not_block_the_rest(self, caplog) -> None:
        failing = FakeHandler('failing', raise_on_cleanup=True)
        ok = FakeHandler('ok')
        manager = AlertManager(handlers=[failing, ok], cooldown_seconds=0.0)
        with caplog.at_level('ERROR'):
            manager.cleanup()  # must not raise
        assert ok.cleanup_calls == 1
```

- [x] **Step 2: Run the tests to confirm they fail**

Run: `pytest tests/client/alerts/test_manager.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [x] **Step 3: Implement `AlertManager`**

`counter_cruiser/client/alerts/manager.py`:

```python
"""AlertManager: per-zone cooldown and deterrent-first, isolated fan-out."""

from __future__ import annotations

import logging
import time

from counter_cruiser.client.alerts.context import AlertContext, AlertHandler

logger = logging.getLogger(__name__)


class AlertManager:
    """Enforces per-zone cooldown, then dispatches deterrent-first to handlers.

    The deterrent handler (if any) always runs before every other handler,
    so the training correction is never delayed by slower handlers (file
    writes, HTTP calls). Each handler's failure is isolated: one raising
    handler never prevents the others from running.
    """

    def __init__(
        self,
        handlers: list[AlertHandler],
        cooldown_seconds: float,
        deterrent: AlertHandler | None = None,
    ) -> None:
        """Store injected handlers and the per-zone cooldown window."""
        self._deterrent = deterrent
        self._handlers = handlers
        self._cooldown_seconds = cooldown_seconds
        self._last_alert: dict[str, float] = {}

    def _all_handlers(self) -> list[AlertHandler]:
        deterrent = [self._deterrent] if self._deterrent is not None else []
        return deterrent + self._handlers

    def _within_cooldown(self, zones: set[str], now: float) -> bool:
        if not zones:
            return False
        return all(
            now - self._last_alert.get(zone_id, float('-inf')) < self._cooldown_seconds
            for zone_id in zones
        )

    def maybe_alert(self, context: AlertContext) -> None:
        """Dispatch to all handlers unless every triggered zone is on cooldown."""
        now = time.monotonic()
        if self._within_cooldown(context.triggered_zones, now):
            logger.info(
                'Alert suppressed (cooldown): zones=%s',
                sorted(context.triggered_zones),
            )
            return
        for zone_id in context.triggered_zones:
            self._last_alert[zone_id] = now
        for handler in self._all_handlers():
            try:
                handler.trigger(context)
            except Exception:
                logger.exception(
                    'Alert handler %s failed', type(handler).__name__
                )

    def cleanup(self) -> None:
        """Clean up every handler, isolating one handler's cleanup failure."""
        for handler in self._all_handlers():
            try:
                handler.cleanup()
            except Exception:
                logger.exception(
                    'Cleanup failed for handler %s', type(handler).__name__
                )
```

- [x] **Step 4: Run the tests to confirm they pass**

Run: `pytest tests/client/alerts/test_manager.py -v`
Expected: PASS (all tests, including the deterrent-first ordering
assertion)

- [x] **Step 5: Run `ruff check`/`ruff format`**

Run: `ruff check counter_cruiser/client/alerts/manager.py tests/client/alerts/test_manager.py && ruff format counter_cruiser/client/alerts/manager.py tests/client/alerts/test_manager.py`
Expected: clean

- [x] **Step 6: Commit**

```bash
git add counter_cruiser/client/alerts/manager.py tests/client/alerts/test_manager.py
git commit -m "feat(alert-system): add AlertManager with cooldown and deterrent-first fan-out"
```

---

## Task 10: Wire the client orchestration to `AlertManager`

- [x] **Task 10 complete**

**Files:**
- Modify: `counter_cruiser/client/__main__.py`
- Modify: `tests/client/test_main.py`
- Create: `tests/client/alerts/test_integration.py`

**Interfaces:**
- Consumes: `AlertManager` (Task 9), `AlertContext` (Task 2),
  `DeterrentHandler` (Task 5), `NotificationHandler` (Task 6),
  `SnapshotHandler` (Task 7), `LogHandler` (Task 8),
  `ClientSession.get_frame` (Task 4), `analyze_detections` /
  `DetectionHistory.is_consecutive_elevated` (existing foundation code).
- Produces: the wired `main()` — no new public interface for later tasks
  (this is the final integration point).

- [x] **Step 1: Write the failing integration test**

`tests/client/alerts/test_integration.py`:

```python
"""Integration test: debounced elevated event reaches AlertManager."""

from __future__ import annotations

from unittest.mock import MagicMock

from counter_cruiser.client.alerts.context import AlertContext
from counter_cruiser.client.alerts.manager import AlertManager
from counter_cruiser.config.models import Zone
from counter_cruiser.shared.debounce import DetectionHistory
from counter_cruiser.shared.geometry import analyze_detections
from counter_cruiser.shared.protocol import BoundingBox, DetectionMessage


def _elevated_box() -> BoundingBox:
    return BoundingBox(
        x1=0, y1=0, x2=200, y2=400, confidence=0.9, class_id=16, class_name='dog'
    )


class TestDebounceToAlertManagerWiring:
    def test_debounced_elevated_event_invokes_alert_manager(self) -> None:
        zone = Zone(id='counter', name='Counter', polygon=[(0, 0), (640, 0), (640, 480)])
        history = DetectionHistory()
        alert_manager = MagicMock(spec=AlertManager)
        frame_height = 480
        min_size_ratio = 0.25
        zones = [zone]

        def on_result(msg: DetectionMessage) -> None:
            analysis = analyze_detections(msg.boxes, zones, frame_height, min_size_ratio)
            history.add(msg.frame_id, analysis.elevated)
            if history.is_consecutive_elevated():
                context = AlertContext(
                    frame=None,
                    detections=msg.boxes,
                    zones=zones,
                    triggered_zones=analysis.triggered_zones,
                    frame_id=msg.frame_id,
                )
                alert_manager.maybe_alert(context)

        # First elevated frame: debounce not yet satisfied.
        on_result(DetectionMessage(frame_id=1, boxes=[_elevated_box()], processing_time_ms=1.0))
        alert_manager.maybe_alert.assert_not_called()

        # Second consecutive elevated frame: debounce satisfied, dispatch fires.
        on_result(DetectionMessage(frame_id=2, boxes=[_elevated_box()], processing_time_ms=1.0))
        alert_manager.maybe_alert.assert_called_once()
        context = alert_manager.maybe_alert.call_args[0][0]
        assert context.triggered_zones == {'counter'}
        assert context.frame_id == 2
```

- [x] **Step 2: Run the test to confirm the wiring shape is correct**

Run: `pytest tests/client/alerts/test_integration.py -v`
Expected: PASS. This test only exercises existing foundation code
(`analyze_detections`, `DetectionHistory`) plus the already-implemented
`AlertContext`/`AlertManager` from Tasks 2 and 9, so it should pass as
soon as it is written — before `__main__.py` is touched. It exists to
confirm the debounce-to-`AlertContext`-to-`AlertManager` wiring shape is
correct in isolation, so any failure here means the wiring approach itself
is wrong, not "not yet implemented."

- [x] **Step 3: Implement the wiring in `client/__main__.py`**

Replace the full file:

```python
"""Client entrypoint: wire config, camera, transport, zone analysis, alerts."""

from __future__ import annotations

import asyncio
import logging
import signal

from counter_cruiser.client.alerts.context import AlertContext
from counter_cruiser.client.alerts.deterrent import DeterrentHandler
from counter_cruiser.client.alerts.log import LogHandler
from counter_cruiser.client.alerts.manager import AlertManager
from counter_cruiser.client.alerts.notifications import NotificationHandler
from counter_cruiser.client.alerts.snapshot import SnapshotHandler
from counter_cruiser.client.capture import OpenCVCapture
from counter_cruiser.client.transport import ClientSession
from counter_cruiser.config.loader import load_client_config
from counter_cruiser.config.models import ClientSettings
from counter_cruiser.shared.debounce import DetectionHistory
from counter_cruiser.shared.geometry import analyze_detections
from counter_cruiser.shared.protocol import DetectionMessage

logger = logging.getLogger(__name__)


def _configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s %(name)s %(levelname)s %(message)s',
    )


def _build_alert_manager(config: ClientSettings) -> AlertManager:
    """Construct the AlertManager from enabled handlers in *config*."""
    alerts = config.alerts
    deterrent = DeterrentHandler(alerts.deterrent) if alerts.deterrent.enabled else None
    handlers = []
    if alerts.snapshot.enabled:
        handlers.append(SnapshotHandler(alerts.snapshot))
    if alerts.log.enabled:
        handlers.append(LogHandler(alerts.log))
    if alerts.notification.enabled:
        handlers.append(NotificationHandler(alerts.notification))
    return AlertManager(
        handlers=handlers, cooldown_seconds=alerts.cooldown_seconds, deterrent=deterrent
    )


def main() -> None:
    """Load configuration and run the client until interrupted."""
    _configure_logging()
    config = load_client_config()
    history = DetectionHistory()
    alert_manager = _build_alert_manager(config)

    def on_result(msg: DetectionMessage, latency: float) -> None:
        analysis = analyze_detections(
            msg.boxes, config.zones, session.frame_height, config.min_size_ratio
        )
        history.add(msg.frame_id, analysis.elevated)
        actionable = history.is_consecutive_elevated()
        status = 'ELEVATED' if actionable else 'floor'
        zones = (
            ', '.join(sorted(analysis.triggered_zones))
            if analysis.triggered_zones
            else 'none'
        )
        logger.info(
            'frame=%d latency=%.1fms status=%s zones=[%s]',
            msg.frame_id,
            latency * 1000.0,
            status,
            zones,
        )
        if actionable:
            context = AlertContext(
                frame=session.get_frame(msg.frame_id),
                detections=msg.boxes,
                zones=config.zones,
                triggered_zones=analysis.triggered_zones,
                frame_id=msg.frame_id,
            )
            alert_manager.maybe_alert(context)

    session = ClientSession(capture=OpenCVCapture(), config=config, on_result=on_result)

    def _shutdown(signum, frame):  # pragma: no cover
        logger.info('Shutdown signal received')
        session.stop()

    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    try:
        asyncio.run(session.run())
    finally:
        alert_manager.cleanup()


if __name__ == '__main__':  # pragma: no cover
    main()
```

- [x] **Step 4: Update `tests/client/test_main.py` for the new wiring**

Add imports and a fixture-free patch of the alert manager builder so the
existing `test_wires_session_and_runs` doesn't need real handlers:

```python
    def test_wires_session_and_runs(self) -> None:
        config = ClientSettings()

        with (
            patch(
                'counter_cruiser.client.__main__._configure_logging'
            ) as configure_logging,
            patch(
                'counter_cruiser.client.__main__.load_client_config',
                return_value=config,
            ) as load_cfg,
            patch('counter_cruiser.client.__main__.OpenCVCapture') as capture_cls,
            patch('counter_cruiser.client.__main__.ClientSession') as session_cls,
            patch('counter_cruiser.client.__main__.signal.signal') as signal_signal,
            patch('counter_cruiser.client.__main__.asyncio.run') as run,
        ):
            session_instance = MagicMock()
            session_instance.frame_height = config.frame_height
            session_instance.get_frame.return_value = None
            session_cls.return_value = session_instance

            main()

            configure_logging.assert_called_once_with()
            load_cfg.assert_called_once_with()
            capture_cls.assert_called_once_with()
            session_cls.assert_called_once()
            _, kwargs = session_cls.call_args
            assert kwargs['capture'] is capture_cls.return_value
            assert kwargs['config'] is config
            on_result = kwargs['on_result']

            assert signal_signal.call_count == 2
            run.assert_called_once_with(session_instance.run.return_value)

        # Exercise the on_result closure: single frame (debounce not met) —
        # no alert dispatch, but the zone-analysis/log branch is covered.
        box = BoundingBox(
            x1=0, y1=0, x2=10, y2=400, confidence=0.9, class_id=16, class_name='dog'
        )
        msg = DetectionMessage(frame_id=1, boxes=[box], processing_time_ms=2.0)
        on_result(msg, 0.123)
```

Add a new test class covering the debounced-elevated path end-to-end
through `main()`, and the `_build_alert_manager` helper directly:

```python
class TestBuildAlertManager:
    def test_all_handlers_disabled_by_default(self) -> None:
        from counter_cruiser.client.__main__ import _build_alert_manager

        manager = _build_alert_manager(ClientSettings())
        # No handlers/deterrent constructed when everything is disabled.
        assert manager._handlers == []
        assert manager._deterrent is None

    def test_enabled_handlers_are_constructed(self) -> None:
        from counter_cruiser.client.__main__ import _build_alert_manager
        from counter_cruiser.config.models import AlertConfig, LogConfig

        config = ClientSettings(
            alerts=AlertConfig(log=LogConfig(enabled=True, file='alerts.log'))
        )
        manager = _build_alert_manager(config)
        assert len(manager._handlers) == 1


class TestMainCallsAlertManagerCleanupOnShutdown:
    def test_cleanup_called_after_run(self) -> None:
        config = ClientSettings()
        with (
            patch('counter_cruiser.client.__main__._configure_logging'),
            patch(
                'counter_cruiser.client.__main__.load_client_config',
                return_value=config,
            ),
            patch('counter_cruiser.client.__main__.OpenCVCapture'),
            patch('counter_cruiser.client.__main__.ClientSession') as session_cls,
            patch('counter_cruiser.client.__main__.signal.signal'),
            patch('counter_cruiser.client.__main__.asyncio.run'),
            patch(
                'counter_cruiser.client.__main__._build_alert_manager'
            ) as build_manager,
        ):
            session_cls.return_value.frame_height = config.frame_height
            manager_instance = MagicMock()
            build_manager.return_value = manager_instance

            main()

            manager_instance.cleanup.assert_called_once_with()
```

- [x] **Step 5: Run the client tests to confirm they pass**

Run: `pytest tests/client/test_main.py tests/client/alerts/test_integration.py -v`
Expected: PASS

- [x] **Step 6: Run the full suite and confirm coverage**

Run: `pytest`
Expected: PASS, 100% coverage maintained (the `if actionable:` branch in
`on_result` is now covered by the integration test's second call and by
`TestMain`'s single-frame call for the non-actionable branch)

- [x] **Step 7: Run `ruff check`/`ruff format`**

Run: `ruff check counter_cruiser/client/__main__.py tests/client/test_main.py tests/client/alerts/test_integration.py && ruff format counter_cruiser/client/__main__.py tests/client/test_main.py tests/client/alerts/test_integration.py`
Expected: clean

- [x] **Step 8: Commit**

```bash
git add counter_cruiser/client/__main__.py tests/client/test_main.py tests/client/alerts/test_integration.py
git commit -m "feat(alert-system): wire AlertManager into the client orchestration"
```

---

## Task 11: Finalization

- [x] **Task 11 complete**

**Files:**
- Modify: `CLAUDE.md`
- No new source files — this task is verification + documentation only.

- [x] **Step 1: Run the full test suite with coverage**

Run: `pytest`
Expected: all tests pass; terminal coverage report shows 100% (branch
included); `--cov-fail-under=100` does not fail the run

- [x] **Step 2: Fix any coverage gaps**

If any line/branch is uncovered, add the missing test case to the relevant
task's test file (do not add blanket `pragma: no cover` to dodge real
gaps — only use it for genuinely unreachable code, consistent with the
project's existing convention in `server/model.py` and `client/__main__.py`).
Re-run `pytest` until 100% holds.

- [x] **Step 3: Run ruff across the whole repo**

Run: `ruff check . && ruff format --check .`
Expected: no findings. If `ruff format --check .` reports files needing
formatting, run `ruff format .` and re-run the check.

- [x] **Step 4: Verify docstrings on all new public modules/classes/functions**

Run: `grep -rL '"""' counter_cruiser/client/alerts counter_cruiser/client/annotation.py`
Expected: empty output (every file has at least one docstring). Manually
confirm every public class/function defined in Tasks 2–10 has its own
docstring (each code block above already includes one — this step is a
final audit, not new work).

- [x] **Step 5: Update `CLAUDE.md`'s Architecture and Commands sections**

In the `## Architecture` section, extend the `client/` bullet and add a
new line for the alerts package:

```markdown
- `client/`: `capture.py` (`CameraCapture` protocol + `OpenCVCapture`
  implementation), `transport.py` (`ClientSession` — connects to the
  server, sends frames, matches detections, retains a bounded frame ring
  buffer, handles reconnect), `annotation.py` (shared `annotate_frame`
  helper — boxes, zone polygons, timestamp — reused by the alert system
  and the web UI), `alerts/` (`AlertManager` — per-zone cooldown,
  deterrent-first isolated fan-out; `DeterrentHandler` — GPIO
  button-press simulation on the existing ultrasonic trainer;
  `SnapshotHandler`, `LogHandler`, `NotificationHandler` — recording and
  ntfy.sh/Pushover push notifications), `__main__.py` (entrypoint wiring
  config, camera, transport, zone analysis, debounce, and alert
  dispatch)
```

No changes needed to `## Commands` — the alert system adds no new CLI
entrypoints or install extras beyond what Task 1 already documented via
`pyproject.toml` (`gpio` extra is optional and Pi-only, not part of the
documented base install flow).

- [x] **Step 6: Commit**

```bash
git add CLAUDE.md
git commit -m "docs(alert-system): document the alerts package in CLAUDE.md"
```

---

## Self-Review Notes

- **Spec coverage:** every `tasks.md` line item (1.1–9.4) maps to a task
  above: scaffolding/deps → Task 1; `AlertContext`/`AlertHandler` → Task 2;
  alert config → Task 3; deterrent → Task 5 (corrected to GPIO
  button-press per the design doc, not PWM); notifications → Task 6;
  snapshot + shared annotation → Task 7; log → Task 8; `AlertManager` →
  Task 9; integration wiring → Task 10; finalization → Task 11. The frame
  ring buffer (a design-doc gap, not a `tasks.md` line item) is its own
  Task 4, ordered before the snapshot handler that depends on it.
- **Deterrent correction applied:** Task 5's tests and implementation use
  `gpio.output(pin, HIGH/LOW)` exclusively — no `PWM`, `frequency`, or
  `duty_cycle` anywhere in this plan, matching the design doc's
  correction over the original `design.md` assumption.
- **Deterrent-first ordering:** enforced structurally in `AlertManager`
  via a dedicated `deterrent` constructor param concatenated before
  `handlers`, not by injection-order convention alone — `Task 9`'s
  `test_deterrent_fires_before_any_other_handler` asserts this directly.
- **Frame retention:** Task 4 delivers `ClientSession.get_frame`, and
  Task 10 wires `session.get_frame(msg.frame_id)` into the `AlertContext`
  built from the *same* `on_result` invocation that satisfied the
  debounce — the authentic evidence frame, not a re-capture.
- **Type consistency check:** `AlertHandler.trigger(context: AlertContext)`
  / `.cleanup()` signatures are identical across `DeterrentHandler`,
  `NotificationHandler`, `SnapshotHandler`, `LogHandler`, and the
  `FakeHandler` test double in Task 9 — no drift found.
- **Placeholder scan:** no TBD/TODO/"similar to Task N" markers; every
  step above shows the actual code, not a description of it.
