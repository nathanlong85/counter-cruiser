---
change: foundation
design-doc: openspec/changes/foundation/design.md
base-ref: 88ab427e765f43596797aa157bcc5af1b21d1a19
---

# Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the installable `counter_cruiser` package with typed config, typed WebSocket protocol, end-to-end detection pipeline (Pi captures → server infers → Pi runs zone analysis), and 100% automated test coverage.

**Architecture:** A single Python package with four sub-packages (`shared/`, `config/`, `client/`, `server/`). The client (Pi) owns cameras and zone analysis; the server (Linux host) owns YOLO inference. They communicate over WebSocket using Pydantic discriminated-union messages. All components are constructed with injected dependencies so every code path is testable headlessly.

**Tech Stack:** Python 3.11+, pydantic v2, pydantic-settings v2, websockets 12+, opencv-python 4.8+, numpy 1.26+, ultralytics 8+ (server only, optional extra), pytest + pytest-asyncio + pytest-cov, ruff, uv.

## Global Constraints

- Python `>=3.11` required (uses `tomllib` from stdlib, `X | Y` union syntax).
- Single-quotes throughout (ruff `format.quote-style = "single"`).
- Line length 88 (ruff default).
- Ruff rule sets: `B, E, F, I, SIM, UP`.
- `extra = 'forbid'` on every pydantic-settings model — unknown keys are errors.
- No `print()` anywhere — use `logging`.
- No import-time side effects — no module-level mutable state.
- No `sys.path` manipulation — package installed via `uv pip install -e .`.
- 100% line + branch coverage; `--cov-fail-under=100` in addopts. Unreachable lines use `# pragma: no cover`.
- Every public module, class, and function has a docstring.
- `DOG_CLASS_ID = 16` (COCO dataset index for "dog").

---

## File Map

```
counter_cruiser/
├── __init__.py
├── shared/
│   ├── __init__.py
│   ├── geometry.py        # check_zones, analyze_dog_position, analyze_detections, FrameAnalysis
│   ├── debounce.py        # DetectionHistory, FrameRecord
│   └── protocol.py        # BoundingBox, message models, AnyMessage union, serialize/deserialize,
│                          #   encode_frame, decode_frame, make_error, make_pong
├── config/
│   ├── __init__.py
│   ├── models.py          # Zone, _BaseConfig, ClientSettings, ServerSettings
│   └── loader.py          # load_client_config, load_server_config
├── client/
│   ├── __init__.py
│   ├── capture.py         # CameraCapture (Protocol), OpenCVCapture
│   ├── transport.py       # ClientSession (send loop + receive loop + reconnect supervisor)
│   └── __main__.py        # client entrypoint: wires config, camera, session, zone analysis
└── server/
    ├── __init__.py
    ├── model.py            # DetectionModel (ABC), YOLOAdapter, select_device, DOG_CLASS_ID
    ├── handler.py          # handle_connection coroutine
    └── __main__.py         # server entrypoint: wires config, model, websockets.serve

tests/
├── conftest.py             # shared fixtures (sample_frame numpy array, sample zone)
├── shared/
│   ├── __init__.py
│   ├── test_geometry.py
│   ├── test_debounce.py
│   └── test_protocol.py
├── config/
│   ├── __init__.py
│   └── test_config.py
├── client/
│   ├── __init__.py
│   ├── test_capture.py
│   └── test_transport.py
├── server/
│   ├── __init__.py
│   ├── test_model.py
│   └── test_handler.py
└── test_integration.py

fixtures/
├── client.toml             # example client config (also used as test fixture)
└── server.toml             # example server config (also used as test fixture)
```

---

## Task 1: Project scaffolding & quality gates

**Files:**
- Create: `pyproject.toml`
- Create: `counter_cruiser/__init__.py` and all sub-package `__init__.py` files
- Create: `tests/__init__.py` and all sub-directory `__init__.py` files
- Create: `tests/conftest.py`

**Interfaces:**
- Produces: installable package; `pytest`, `ruff check .`, `ruff format --check .` all exit 0.

- [x] **Step 1.1 — Initialize the package with uv**

```bash
cd /Users/nate/repos/counter-cruiser
uv init --no-workspace --python 3.11 --name counter-cruiser 2>/dev/null || true
```

Create `pyproject.toml` with this exact content (overwrite what uv generated):

```toml
[project]
name = "counter-cruiser"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
    "pydantic>=2.7",
    "pydantic-settings>=2.3",
    "websockets>=12.0",
    "opencv-python>=4.10",
    "numpy>=1.26",
]

[project.optional-dependencies]
server = [
    "torch>=2.3",
    "ultralytics>=8.2",
]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.23",
    "pytest-cov>=5.0",
    "ruff>=0.6",
]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.ruff]
line-length = 88

[tool.ruff.lint]
select = ["B", "E", "F", "I", "SIM", "UP"]

[tool.ruff.format]
quote-style = "single"

[tool.pytest.ini_options]
asyncio_mode = "auto"
markers = [
    "unit: unit tests",
    "integration: integration tests",
    "e2e: end-to-end tests",
]
strict_markers = true
addopts = "--strict-markers --cov=counter_cruiser --cov-report=term-missing --cov-fail-under=100"

[tool.coverage.report]
exclude_lines = [
    "pragma: no cover",
    "if __name__ == .__main__.:",
    "@(abc\\.)?abstractmethod",
    "def __repr__",
]
```

- [x] **Step 1.2 — Create package skeleton**

```bash
mkdir -p counter_cruiser/{shared,config,client,server}
mkdir -p tests/{shared,config,client,server}
mkdir -p fixtures
```

Create each `__init__.py` as an empty file with a module docstring:

`counter_cruiser/__init__.py`:
```python
"""counter-cruiser: automated dog-deterrent system."""
```

`counter_cruiser/shared/__init__.py`:
```python
"""Shared protocol models, geometry helpers, and debounce logic."""
```

`counter_cruiser/config/__init__.py`:
```python
"""Typed, validated configuration for client and server components."""
```

`counter_cruiser/client/__init__.py`:
```python
"""Client-side camera capture, frame transport, and zone analysis orchestration."""
```

`counter_cruiser/server/__init__.py`:
```python
"""Server-side detection model abstraction and WebSocket connection handler."""
```

Create `tests/__init__.py`, `tests/shared/__init__.py`, `tests/config/__init__.py`, `tests/client/__init__.py`, `tests/server/__init__.py` — all empty (no docstring needed for test packages).

- [x] **Step 1.3 — Install in editable mode with dev extras**

```bash
uv pip install -e ".[dev]"
```

Expected: resolves and installs without errors. `counter_cruiser` is importable.

- [x] **Step 1.4 — Create the shared test fixtures conftest**

`tests/conftest.py`:
```python
"""Shared test fixtures."""
import numpy as np
import pytest

from counter_cruiser.config.models import Zone


@pytest.fixture()
def sample_frame() -> np.ndarray:
    """640x480 BGR frame filled with zeros (black)."""
    return np.zeros((480, 640, 3), dtype=np.uint8)


@pytest.fixture()
def full_frame_zone() -> Zone:
    """A zone that covers the entire 640x480 frame."""
    return Zone(
        id='counter',
        name='Counter',
        enabled=True,
        polygon=[(0, 0), (640, 0), (640, 480), (0, 480)],
    )
```

Note: this fixture imports `Zone` which does not exist yet — that is expected. Pytest will collect this file but fail gracefully until Task 5 is done. The fixture is defined here so later tasks can use it.

- [x] **Step 1.5 — Verify ruff config works**

```bash
ruff check . && ruff format --check .
```

Expected: exits 0 with no findings (only `__init__.py` stubs exist so far). If ruff complains about missing trailing newline, add one.

- [x] **Step 1.6 — Commit**

```bash
git add pyproject.toml counter_cruiser/ tests/ fixtures/
git commit -m "feat: initialize counter_cruiser package skeleton with quality gate config"
```

---

## Task 2: Shared geometry — containment (tasks.md 2.1–2.2)

**Files:**
- Create: `counter_cruiser/shared/geometry.py`
- Create: `tests/shared/test_geometry.py`

**Interfaces:**
- Consumes: `BoundingBox` from `counter_cruiser.shared.protocol` (not yet written — define a local stub in tests until Task 6 lands, OR implement protocol first; plan assumes protocol is done first — see ordering note below).

> **Ordering note:** Tasks 2–3 (geometry) depend on `BoundingBox` which lives in Task 6 (protocol). Implement Task 6 (protocol models only, steps 4.1–4.2) before starting Task 2, OR stub `BoundingBox` locally in the geometry module and merge later. **Recommended: do Task 4 before Task 2.** The plan preserves tasks.md order for reference but the implementer should execute in this order: 1 → 4.1-4.4 → 2 → 3 → 4.5-4.8 → 5 → 6 → 7 → 8 → 9 → 10 → 11.

- Produces:
  - `check_zones(box: BoundingBox, zones: list[Zone]) -> list[str]`
  - `box_test_points(box: BoundingBox) -> list[tuple[float, float]]`

- [ ] **Step 2.1 — Write failing tests for check_zones**

`tests/shared/test_geometry.py` (add this section):
```python
"""Tests for shared geometry helpers."""
import numpy as np
import pytest

from counter_cruiser.config.models import Zone
from counter_cruiser.shared.geometry import check_zones
from counter_cruiser.shared.protocol import BoundingBox


def _zone(
    id: str = 'z1',
    polygon: list[tuple[int, int]] | None = None,
    enabled: bool = True,
) -> Zone:
    if polygon is None:
        polygon = [(100, 100), (300, 100), (300, 300), (100, 300)]
    return Zone(id=id, name=id, enabled=enabled, polygon=polygon)


def _box(x1: int = 150, y1: int = 150, x2: int = 250, y2: int = 250) -> BoundingBox:
    return BoundingBox(x1=x1, y1=y1, x2=x2, y2=y2, confidence=0.9, class_id=16, class_name='dog')


class TestCheckZones:
    def test_point_inside_zone_triggers_it(self) -> None:
        box = _box(150, 150, 250, 250)  # center (200,200) inside z1 square
        result = check_zones(box, [_zone('z1')])
        assert result == ['z1']

    def test_box_outside_all_zones_triggers_nothing(self) -> None:
        box = _box(400, 400, 500, 500)  # entirely outside z1 (100-300,100-300)
        result = check_zones(box, [_zone('z1')])
        assert result == []

    def test_disabled_zone_is_ignored(self) -> None:
        box = _box(150, 150, 250, 250)
        result = check_zones(box, [_zone('z1', enabled=False)])
        assert result == []

    def test_box_can_trigger_multiple_zones(self) -> None:
        z1 = _zone('z1', polygon=[(0, 0), (300, 0), (300, 300), (0, 300)])
        z2 = _zone('z2', polygon=[(100, 100), (400, 100), (400, 400), (100, 400)])
        box = _box(150, 150, 250, 250)  # center (200,200) inside both
        result = check_zones(box, [z1, z2])
        assert sorted(result) == ['z1', 'z2']

    def test_no_zones_returns_empty(self) -> None:
        assert check_zones(_box(), []) == []
```

- [ ] **Step 2.2 — Run tests to confirm they fail**

```bash
pytest tests/shared/test_geometry.py::TestCheckZones -v
```

Expected: ImportError or AttributeError (geometry module does not exist yet).

- [ ] **Step 2.3 — Implement check_zones**

`counter_cruiser/shared/geometry.py`:
```python
"""Pure geometry helpers for zone containment and elevated-dog classification."""
from __future__ import annotations

import cv2
import numpy as np

from counter_cruiser.config.models import Zone
from counter_cruiser.shared.protocol import BoundingBox


def box_test_points(box: BoundingBox) -> list[tuple[float, float]]:
    """Return the four corners and centre of a bounding box."""
    cx = (box.x1 + box.x2) / 2.0
    cy = (box.y1 + box.y2) / 2.0
    return [
        (float(box.x1), float(box.y1)),
        (float(box.x2), float(box.y1)),
        (float(box.x2), float(box.y2)),
        (float(box.x1), float(box.y2)),
        (cx, cy),
    ]


def check_zones(box: BoundingBox, zones: list[Zone]) -> list[str]:
    """Return zone ids whose polygon contains any test point of *box*.

    Disabled zones are always skipped.
    """
    triggered: list[str] = []
    for zone in zones:
        if not zone.enabled:
            continue
        polygon = np.array(zone.polygon, dtype=np.float32)
        for pt in box_test_points(box):
            if cv2.pointPolygonTest(polygon, pt, False) >= 0:
                triggered.append(zone.id)
                break
    return triggered
```

- [ ] **Step 2.4 — Run tests to confirm they pass**

```bash
pytest tests/shared/test_geometry.py::TestCheckZones -v
```

Expected: 5 tests pass.

- [ ] **Step 2.5 — Commit**

```bash
git add counter_cruiser/shared/geometry.py tests/shared/test_geometry.py
git commit -m "feat: implement check_zones with point-in-polygon containment"
```

---

## Task 3: Shared geometry — elevated decision & aggregate (tasks.md 2.3–2.6)

**Files:**
- Modify: `counter_cruiser/shared/geometry.py`
- Modify: `tests/shared/test_geometry.py`

**Interfaces:**
- Produces:
  - `FrameAnalysis` dataclass: `elevated: bool`, `triggered_zones: set[str]`
  - `analyze_dog_position(box, zones, frame_height, min_size_ratio) -> tuple[bool, list[str]]`
  - `analyze_detections(boxes, zones, frame_height, min_size_ratio) -> FrameAnalysis`

- [ ] **Step 3.1 — Write failing tests for analyze_dog_position**

Append to `tests/shared/test_geometry.py`:
```python
from counter_cruiser.shared.geometry import analyze_dog_position


class TestAnalyzeDogPosition:
    """size_ratio = box_height / frame_height; elevated = ratio > min AND in zone."""

    def test_large_dog_in_zone_is_elevated(self) -> None:
        box = _box(100, 0, 200, 300)  # height=300, frame=480 → ratio=0.625 > 0.25; inside z1
        z = _zone('z1', polygon=[(0, 0), (640, 0), (640, 480), (0, 480)])
        elevated, zones = analyze_dog_position(box, [z], frame_height=480, min_size_ratio=0.25)
        assert elevated is True
        assert zones == ['z1']

    def test_large_dog_outside_zone_not_elevated(self) -> None:
        box = _box(0, 0, 100, 300)  # height=300 > 0.25×480; but outside z1 (100-300,100-300)
        elevated, zones = analyze_dog_position(
            box, [_zone('z1')], frame_height=480, min_size_ratio=0.25
        )
        assert elevated is False
        assert zones == []

    def test_small_dog_in_zone_not_elevated(self) -> None:
        box = _box(150, 150, 250, 200)  # height=50; ratio≈0.10 < 0.25; inside z1
        elevated, zones = analyze_dog_position(
            box, [_zone('z1')], frame_height=480, min_size_ratio=0.25
        )
        assert elevated is False
        assert zones == ['z1']

    def test_size_ratio_computed_from_frame_height(self) -> None:
        """Box height == min threshold exactly → not elevated (strictly greater)."""
        # box height = 120, frame_height = 480, ratio = 0.25 == min_size_ratio → NOT elevated
        box = _box(150, 100, 250, 220)  # height=120
        z = _zone('z1', polygon=[(0, 0), (640, 0), (640, 480), (0, 480)])
        elevated, _ = analyze_dog_position(box, [z], frame_height=480, min_size_ratio=0.25)
        assert elevated is False
```

- [ ] **Step 3.2 — Run to confirm failure**

```bash
pytest tests/shared/test_geometry.py::TestAnalyzeDogPosition -v
```

Expected: ImportError for `analyze_dog_position`.

- [ ] **Step 3.3 — Implement analyze_dog_position**

Append to `counter_cruiser/shared/geometry.py`:
```python
def analyze_dog_position(
    box: BoundingBox,
    zones: list[Zone],
    frame_height: int,
    min_size_ratio: float,
) -> tuple[bool, list[str]]:
    """Classify a single detection as elevated or floor.

    Returns (is_elevated, list_of_triggered_zone_ids).
    Elevated requires size_ratio > min_size_ratio AND at least one zone triggered.
    """
    size_ratio = (box.y2 - box.y1) / frame_height
    triggered = check_zones(box, zones)
    is_elevated = size_ratio > min_size_ratio and len(triggered) > 0
    return is_elevated, triggered
```

- [ ] **Step 3.4 — Write failing tests for FrameAnalysis + analyze_detections**

Append to `tests/shared/test_geometry.py`:
```python
from counter_cruiser.shared.geometry import FrameAnalysis, analyze_detections


class TestAnalyzeDetections:
    _full_zone = Zone(
        id='z1', name='Zone 1', enabled=True,
        polygon=[(0, 0), (640, 0), (640, 480), (0, 480)],
    )

    def _big_box(self) -> BoundingBox:
        """Box with height=300 → ratio=0.625 > 0.25; inside full zone."""
        return BoundingBox(x1=0, y1=0, x2=100, y2=300, confidence=0.9, class_id=16, class_name='dog')

    def _small_box(self) -> BoundingBox:
        """Box with height=50 → ratio≈0.10 < 0.25."""
        return BoundingBox(x1=0, y1=0, x2=100, y2=50, confidence=0.9, class_id=16, class_name='dog')

    def test_any_elevated_marks_frame_elevated(self) -> None:
        result = analyze_detections(
            [self._small_box(), self._big_box()], [self._full_zone], 480, 0.25
        )
        assert result.elevated is True

    def test_triggered_zones_unioned_across_elevated(self) -> None:
        z2 = Zone(id='z2', name='Zone 2', enabled=True, polygon=[(0, 0), (640, 0), (640, 480), (0, 480)])
        result = analyze_detections(
            [self._big_box(), self._big_box()], [self._full_zone, z2], 480, 0.25
        )
        assert result.triggered_zones == {'z1', 'z2'}

    def test_no_detections_returns_not_elevated(self) -> None:
        result = analyze_detections([], [self._full_zone], 480, 0.25)
        assert result.elevated is False
        assert result.triggered_zones == set()

    def test_result_is_frame_analysis(self) -> None:
        result = analyze_detections([], [], 480, 0.25)
        assert isinstance(result, FrameAnalysis)
```

- [ ] **Step 3.5 — Implement FrameAnalysis and analyze_detections**

Add at top of `counter_cruiser/shared/geometry.py` (after imports, before other functions):
```python
from dataclasses import dataclass, field


@dataclass
class FrameAnalysis:
    """Aggregate analysis result for a single video frame."""

    elevated: bool
    triggered_zones: set[str] = field(default_factory=set)
```

Append the function:
```python
def analyze_detections(
    boxes: list[BoundingBox],
    zones: list[Zone],
    frame_height: int,
    min_size_ratio: float,
) -> FrameAnalysis:
    """Aggregate per-box results into a single frame-level analysis."""
    all_zones: set[str] = set()
    elevated = False
    for box in boxes:
        is_el, zone_ids = analyze_dog_position(box, zones, frame_height, min_size_ratio)
        if is_el:
            elevated = True
            all_zones.update(zone_ids)
    return FrameAnalysis(elevated=elevated, triggered_zones=all_zones)
```

- [ ] **Step 3.6 — Run all geometry tests**

```bash
pytest tests/shared/test_geometry.py -v
```

Expected: all tests pass.

- [ ] **Step 3.7 — Commit**

```bash
git add counter_cruiser/shared/geometry.py tests/shared/test_geometry.py
git commit -m "feat: implement elevated-dog decision and frame-level aggregation"
```

---

## Task 4: Consecutive-detection debouncing (tasks.md 3.1–3.2)

**Files:**
- Create: `counter_cruiser/shared/debounce.py`
- Create: `tests/shared/test_debounce.py`

**Interfaces:**
- Produces:
  - `class DetectionHistory`: `add(frame_id: int, is_elevated: bool) -> None`, `is_consecutive_elevated(max_gap: int = 2) -> bool`

- [x] **Step 4.1 — Write failing tests**

`tests/shared/test_debounce.py`:
```python
"""Tests for consecutive-detection debouncing."""
import pytest

from counter_cruiser.shared.debounce import DetectionHistory


class TestDetectionHistory:
    def test_two_consecutive_elevated_meets_condition(self) -> None:
        h = DetectionHistory()
        h.add(1, is_elevated=True)
        h.add(2, is_elevated=True)
        assert h.is_consecutive_elevated() is True

    def test_single_elevated_does_not_meet_condition(self) -> None:
        h = DetectionHistory()
        h.add(1, is_elevated=True)
        assert h.is_consecutive_elevated() is False

    def test_elevated_frames_too_far_apart_do_not_meet(self) -> None:
        h = DetectionHistory()
        h.add(1, is_elevated=True)
        h.add(10, is_elevated=True)  # gap=9 > max_gap=2
        assert h.is_consecutive_elevated() is False

    def test_elevated_within_max_gap_meets(self) -> None:
        h = DetectionHistory()
        h.add(1, is_elevated=True)
        h.add(3, is_elevated=True)  # gap=2 == max_gap → meets condition
        assert h.is_consecutive_elevated() is True

    def test_out_of_order_results_evaluated_by_frame_id(self) -> None:
        h = DetectionHistory()
        h.add(5, is_elevated=True)
        h.add(3, is_elevated=True)  # added after but frame_id=3 < 5 → gap=2 → meets
        assert h.is_consecutive_elevated() is True

    def test_history_is_bounded(self) -> None:
        h = DetectionHistory(max_size=5)
        for i in range(10):
            h.add(i, is_elevated=False)
        assert len(h._records) == 5

    def test_oldest_entries_discarded_when_bounded(self) -> None:
        h = DetectionHistory(max_size=3)
        for i in range(5):
            h.add(i, is_elevated=False)
        # Only frames 2,3,4 should remain
        frame_ids = [r.frame_id for r in h._records]
        assert frame_ids == [2, 3, 4]

    def test_non_elevated_frames_between_elevated_still_meets(self) -> None:
        h = DetectionHistory()
        h.add(1, is_elevated=True)
        h.add(2, is_elevated=False)
        h.add(3, is_elevated=True)  # gap between elevated[0] and elevated[1] = 2 → meets
        assert h.is_consecutive_elevated() is True
```

- [x] **Step 4.2 — Run to confirm failure**

```bash
pytest tests/shared/test_debounce.py -v
```

Expected: ModuleNotFoundError.

- [x] **Step 4.3 — Implement DetectionHistory**

`counter_cruiser/shared/debounce.py`:
```python
"""Consecutive-detection debouncing for the zone-analysis pipeline."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class FrameRecord:
    """A single frame's elevated classification result."""

    frame_id: int
    is_elevated: bool


class DetectionHistory:
    """Bounded sliding window of recent frame results.

    Considers the elevated state actionable only when at least two elevated
    frames appear within *max_gap* frame-id distance, tolerating non-elevated
    frames between them.
    """

    def __init__(self, max_size: int = 20) -> None:
        """Create history with a fixed maximum capacity."""
        self._records: list[FrameRecord] = []
        self._max_size = max_size

    def add(self, frame_id: int, is_elevated: bool) -> None:
        """Record the result for *frame_id*, discarding oldest if at capacity."""
        self._records.append(FrameRecord(frame_id=frame_id, is_elevated=is_elevated))
        if len(self._records) > self._max_size:
            self._records = self._records[-self._max_size :]

    def is_consecutive_elevated(self, max_gap: int = 2) -> bool:
        """Return True if any two elevated frames in history have frame-id gap <= max_gap."""
        elevated = sorted(
            (r for r in self._records if r.is_elevated),
            key=lambda r: r.frame_id,
        )
        if len(elevated) < 2:
            return False
        return any(
            elevated[i + 1].frame_id - elevated[i].frame_id <= max_gap
            for i in range(len(elevated) - 1)
        )
```

- [x] **Step 4.4 — Run tests**

```bash
pytest tests/shared/test_debounce.py -v
```

Expected: all 8 tests pass.

- [x] **Step 4.5 — Commit**

```bash
git add counter_cruiser/shared/debounce.py tests/shared/test_debounce.py
git commit -m "feat: implement bounded detection history with consecutive-elevated debouncing"
```

---

## Task 5: Protocol — models, serialization, frame codec, helpers (tasks.md 4.1–4.8)

**Files:**
- Create: `counter_cruiser/shared/protocol.py`
- Create: `tests/shared/test_protocol.py`

**Interfaces:**
- Produces:
  - `BoundingBox(BaseModel)`: `x1, y1, x2, y2: int`, `confidence: float`, `class_id: int`, `class_name: str`
  - `FrameMessage`, `DetectionMessage`, `ErrorMessage`, `PingMessage`, `PongMessage` — all with `type` literal + `timestamp: datetime`
  - `AnyMessage` — discriminated union on `type`
  - `serialize(msg) -> str`
  - `deserialize(data: str) -> AnyMessage`
  - `encode_frame(frame: np.ndarray, frame_id: int, quality: int = 85) -> FrameMessage`
  - `decode_frame(msg: FrameMessage) -> tuple[np.ndarray, int]`
  - `make_error(error_type, message, frame_id=None) -> ErrorMessage`
  - `make_pong(ping: PingMessage) -> PongMessage`

- [x] **Step 5.1 — Write failing tests for message models**

`tests/shared/test_protocol.py`:
```python
"""Tests for typed WebSocket protocol models."""
from __future__ import annotations

import json
from datetime import datetime, timezone

import numpy as np
import pytest

from counter_cruiser.shared.protocol import (
    BoundingBox,
    DetectionMessage,
    ErrorMessage,
    FrameMessage,
    PingMessage,
    PongMessage,
    decode_frame,
    deserialize,
    encode_frame,
    make_error,
    make_pong,
    serialize,
)


class TestMessageModels:
    def test_bounding_box_fields(self) -> None:
        box = BoundingBox(x1=10, y1=20, x2=100, y2=200, confidence=0.9, class_id=16, class_name='dog')
        assert box.x1 == 10
        assert box.confidence == 0.9
        assert box.class_name == 'dog'

    def test_frame_message_has_type_discriminator(self) -> None:
        msg = FrameMessage(frame_id=1, image_data='abc', width=640, height=480)
        assert msg.type == 'frame'

    def test_detection_message_has_type_discriminator(self) -> None:
        msg = DetectionMessage(frame_id=1, boxes=[], processing_time_ms=12.5)
        assert msg.type == 'detection'

    def test_error_message_has_type_discriminator(self) -> None:
        msg = ErrorMessage(error_type='oops', message='something broke')
        assert msg.type == 'error'

    def test_ping_has_type_discriminator(self) -> None:
        assert PingMessage().type == 'ping'

    def test_pong_has_type_discriminator(self) -> None:
        ping = PingMessage()
        assert PongMessage(ping_timestamp=ping.timestamp).type == 'pong'

    def test_all_messages_carry_timestamp(self) -> None:
        for msg in [
            FrameMessage(frame_id=1, image_data='x', width=1, height=1),
            DetectionMessage(frame_id=1, boxes=[], processing_time_ms=0.0),
            ErrorMessage(error_type='e', message='m'),
            PingMessage(),
            PongMessage(ping_timestamp=datetime.now(timezone.utc)),
        ]:
            assert isinstance(msg.timestamp, datetime)


class TestSerializeDeserialize:
    def test_round_trip_frame_message(self) -> None:
        original = FrameMessage(frame_id=42, image_data='abc==', width=640, height=480)
        restored = deserialize(serialize(original))
        assert isinstance(restored, FrameMessage)
        assert restored.frame_id == 42
        assert restored.image_data == 'abc=='

    def test_round_trip_detection_message(self) -> None:
        box = BoundingBox(x1=0, y1=0, x2=10, y2=10, confidence=0.8, class_id=16, class_name='dog')
        original = DetectionMessage(frame_id=7, boxes=[box], processing_time_ms=5.0)
        restored = deserialize(serialize(original))
        assert isinstance(restored, DetectionMessage)
        assert restored.boxes[0].confidence == pytest.approx(0.8)

    def test_deserialize_dispatches_by_type(self) -> None:
        raw = json.dumps({'type': 'ping', 'timestamp': datetime.now(timezone.utc).isoformat()})
        msg = deserialize(raw)
        assert isinstance(msg, PingMessage)

    def test_malformed_json_raises(self) -> None:
        with pytest.raises(Exception):
            deserialize('not-json')

    def test_unknown_type_raises(self) -> None:
        raw = json.dumps({'type': 'unknown_xyz', 'timestamp': datetime.now(timezone.utc).isoformat()})
        with pytest.raises(Exception):
            deserialize(raw)


class TestFrameCodec:
    def test_encode_produces_frame_message(self, sample_frame: np.ndarray) -> None:
        msg = encode_frame(sample_frame, frame_id=5, quality=85)
        assert isinstance(msg, FrameMessage)
        assert msg.frame_id == 5
        assert msg.width == 640
        assert msg.height == 480
        assert len(msg.image_data) > 0

    def test_decode_recovers_compatible_frame(self, sample_frame: np.ndarray) -> None:
        msg = encode_frame(sample_frame, frame_id=3, quality=85)
        recovered, frame_id = decode_frame(msg)
        assert frame_id == 3
        assert recovered.shape == sample_frame.shape

    def test_encode_failure_raises(self) -> None:
        bad_frame = np.zeros((0, 0, 3), dtype=np.uint8)  # zero-dimension → encoder fails
        with pytest.raises(ValueError, match='JPEG encoding failed'):
            encode_frame(bad_frame, frame_id=1, quality=85)


class TestErrorAndPingPong:
    def test_make_error_without_frame_id(self) -> None:
        err = make_error('timeout', 'connection timed out')
        assert err.error_type == 'timeout'
        assert err.message == 'connection timed out'
        assert err.frame_id is None

    def test_make_error_with_frame_id(self) -> None:
        err = make_error('decode_error', 'bad jpeg', frame_id=7)
        assert err.frame_id == 7

    def test_make_pong_echoes_ping_timestamp(self) -> None:
        ping = PingMessage()
        pong = make_pong(ping)
        assert pong.ping_timestamp == ping.timestamp
```

- [x] **Step 5.2 — Run to confirm failures**

```bash
pytest tests/shared/test_protocol.py -v
```

Expected: ModuleNotFoundError.

- [x] **Step 5.3 — Implement protocol.py**

`counter_cruiser/shared/protocol.py`:
```python
"""Typed WebSocket protocol models and codec utilities.

All messages carry a ``type`` literal for discriminated-union deserialization
and a UTC ``timestamp``. Frames are JPEG-encoded and base64-embedded in JSON.
"""
from __future__ import annotations

import base64
from datetime import datetime, timezone
from typing import Annotated, Literal, Union

import cv2
import numpy as np
from pydantic import BaseModel, Field, TypeAdapter


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Shared sub-models
# ---------------------------------------------------------------------------


class BoundingBox(BaseModel):
    """A single object-detection result with pixel coordinates."""

    x1: int
    y1: int
    x2: int
    y2: int
    confidence: float
    class_id: int
    class_name: str


# ---------------------------------------------------------------------------
# Message models
# ---------------------------------------------------------------------------


class FrameMessage(BaseModel):
    """Client → server: a JPEG-encoded camera frame."""

    type: Literal['frame'] = 'frame'
    frame_id: int
    image_data: str  # base64-encoded JPEG bytes
    width: int
    height: int
    timestamp: datetime = Field(default_factory=_utcnow)


class DetectionMessage(BaseModel):
    """Server → client: inference results for one frame."""

    type: Literal['detection'] = 'detection'
    frame_id: int
    boxes: list[BoundingBox]
    processing_time_ms: float
    timestamp: datetime = Field(default_factory=_utcnow)


class ErrorMessage(BaseModel):
    """Server → client: a processing failure."""

    type: Literal['error'] = 'error'
    error_type: str
    message: str
    frame_id: int | None = None
    timestamp: datetime = Field(default_factory=_utcnow)


class PingMessage(BaseModel):
    """Either direction: connection health check."""

    type: Literal['ping'] = 'ping'
    timestamp: datetime = Field(default_factory=_utcnow)


class PongMessage(BaseModel):
    """Reply to a ping, echoing the ping timestamp."""

    type: Literal['pong'] = 'pong'
    ping_timestamp: datetime
    timestamp: datetime = Field(default_factory=_utcnow)


# ---------------------------------------------------------------------------
# Discriminated union + adapter (created once at import time)
# ---------------------------------------------------------------------------

AnyMessage = Annotated[
    Union[FrameMessage, DetectionMessage, ErrorMessage, PingMessage, PongMessage],
    Field(discriminator='type'),
]

_ADAPTER: TypeAdapter[AnyMessage] = TypeAdapter(AnyMessage)

# ---------------------------------------------------------------------------
# Serialization
# ---------------------------------------------------------------------------


def serialize(
    msg: FrameMessage | DetectionMessage | ErrorMessage | PingMessage | PongMessage,
) -> str:
    """Serialize a message model to a JSON string."""
    return msg.model_dump_json()


def deserialize(data: str) -> FrameMessage | DetectionMessage | ErrorMessage | PingMessage | PongMessage:
    """Deserialize a JSON string to the correct typed message model.

    Raises ``pydantic.ValidationError`` for malformed payloads or unknown types.
    """
    return _ADAPTER.validate_json(data)


# ---------------------------------------------------------------------------
# Frame codec
# ---------------------------------------------------------------------------


def encode_frame(frame: np.ndarray, frame_id: int, quality: int = 85) -> FrameMessage:
    """JPEG-encode *frame* and pack it into a :class:`FrameMessage`.

    Raises ``ValueError`` if the encoder fails (e.g. zero-dimension array).
    """
    ok, buf = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, quality])
    if not ok:
        raise ValueError(f'JPEG encoding failed for frame {frame_id}')
    h, w = frame.shape[:2]
    image_data = base64.b64encode(buf.tobytes()).decode('ascii')
    return FrameMessage(frame_id=frame_id, image_data=image_data, width=w, height=h)


def decode_frame(msg: FrameMessage) -> tuple[np.ndarray, int]:
    """Decode a :class:`FrameMessage` back to a numpy BGR array.

    Returns ``(frame_array, frame_id)``.
    """
    buf = base64.b64decode(msg.image_data)
    arr = np.frombuffer(buf, dtype=np.uint8)
    frame = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    return frame, msg.frame_id


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_error(
    error_type: str, message: str, frame_id: int | None = None
) -> ErrorMessage:
    """Construct an :class:`ErrorMessage`."""
    return ErrorMessage(error_type=error_type, message=message, frame_id=frame_id)


def make_pong(ping: PingMessage) -> PongMessage:
    """Construct a :class:`PongMessage` echoing *ping*'s timestamp."""
    return PongMessage(ping_timestamp=ping.timestamp)
```

- [x] **Step 5.4 — Run protocol tests**

```bash
pytest tests/shared/test_protocol.py -v
```

Expected: all tests pass.

- [x] **Step 5.5 — Commit**

```bash
git add counter_cruiser/shared/protocol.py tests/shared/test_protocol.py
git commit -m "feat: implement typed WebSocket protocol models, serialization, and frame codec"
```

---

## Task 6: Configuration — Zone, ClientSettings, ServerSettings, TOML loader (tasks.md 5.1–5.7)

**Files:**
- Create: `counter_cruiser/config/models.py`
- Create: `counter_cruiser/config/loader.py`
- Create: `tests/config/test_config.py`
- Create: `fixtures/client.toml`
- Create: `fixtures/server.toml`

**Interfaces:**
- Consumes: nothing from this codebase.
- Produces:
  - `Zone(BaseModel)`: `id: str`, `name: str`, `enabled: bool = True`, `polygon: list[tuple[int, int]]` (validated min 3 points)
  - `ClientSettings(BaseSettings)`: see fields below; `extra='forbid'`
  - `ServerSettings(BaseSettings)`: see fields below; `extra='forbid'`
  - `load_client_config(path: Path | None = None) -> ClientSettings`
  - `load_server_config(path: Path | None = None) -> ServerSettings`

**ClientSettings fields:** `server_host: str = 'localhost'`, `server_port: int = 8765`, `camera_index: int = 0`, `frame_width: int = 640`, `frame_height: int = 480`, `jpeg_quality: int = 85` (1–100), `frame_skip: int = 3` (≥1), `min_size_ratio: float = 0.25` (0.0–1.0), `zones: list[Zone] = []`

**ServerSettings fields:** `host: str = '0.0.0.0'`, `port: int = 8765`, `model_name: str = 'yolov8n.pt'`, `device: str = 'auto'`, `confidence_threshold: float = 0.5` (0.0–1.0)

- [x] **Step 6.1 — Write failing tests**

`tests/config/test_config.py`:
```python
"""Tests for configuration models and TOML loading."""
from __future__ import annotations

import os
from pathlib import Path

import pytest
from pydantic import ValidationError

from counter_cruiser.config.loader import load_client_config, load_server_config
from counter_cruiser.config.models import ClientSettings, ServerSettings, Zone


class TestZoneModel:
    def test_valid_zone_loads(self) -> None:
        z = Zone(id='z1', name='Counter', polygon=[(0, 0), (100, 0), (100, 100)])
        assert z.id == 'z1'
        assert z.enabled is True  # default

    def test_fewer_than_three_points_rejected(self) -> None:
        with pytest.raises(ValidationError, match='at least 3 points'):
            Zone(id='z1', name='Bad', polygon=[(0, 0), (1, 1)])

    def test_no_zones_config_is_valid(self) -> None:
        c = ClientSettings()
        assert c.zones == []


class TestClientSettings:
    def test_defaults_are_sensible(self) -> None:
        c = ClientSettings()
        assert c.server_host == 'localhost'
        assert c.server_port == 8765
        assert c.jpeg_quality == 85
        assert c.frame_skip == 3
        assert 0.0 <= c.min_size_ratio <= 1.0

    def test_jpeg_quality_out_of_range_rejected(self) -> None:
        with pytest.raises(ValidationError):
            ClientSettings(jpeg_quality=0)
        with pytest.raises(ValidationError):
            ClientSettings(jpeg_quality=101)

    def test_min_size_ratio_out_of_range_rejected(self) -> None:
        with pytest.raises(ValidationError):
            ClientSettings(min_size_ratio=-0.1)
        with pytest.raises(ValidationError):
            ClientSettings(min_size_ratio=1.1)

    def test_frame_skip_below_one_rejected(self) -> None:
        with pytest.raises(ValidationError):
            ClientSettings(frame_skip=0)

    def test_unknown_key_rejected(self) -> None:
        with pytest.raises(ValidationError):
            ClientSettings(nonexistent_key='boom')


class TestServerSettings:
    def test_defaults_are_sensible(self) -> None:
        s = ServerSettings()
        assert s.host == '0.0.0.0'
        assert s.port == 8765
        assert s.model_name == 'yolov8n.pt'
        assert s.device == 'auto'
        assert s.confidence_threshold == pytest.approx(0.5)

    def test_confidence_out_of_range_rejected(self) -> None:
        with pytest.raises(ValidationError):
            ServerSettings(confidence_threshold=1.5)

    def test_unknown_key_rejected(self) -> None:
        with pytest.raises(ValidationError):
            ServerSettings(mystery='field')


class TestTomlLoading:
    def test_load_from_explicit_path(self, tmp_path: Path) -> None:
        cfg = tmp_path / 'client.toml'
        cfg.write_text('[counter_cruiser]\nserver_port = 9999\n')
        result = load_client_config(cfg)
        assert result.server_port == 9999

    def test_missing_file_returns_defaults(self, tmp_path: Path) -> None:
        result = load_client_config(tmp_path / 'nonexistent.toml')
        assert result == ClientSettings()

    def test_env_var_overrides_file_value(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        cfg = tmp_path / 'client.toml'
        cfg.write_text('[counter_cruiser]\nserver_port = 9999\n')
        monkeypatch.setenv('COUNTER_CRUISER_SERVER_PORT', '7777')
        result = load_client_config(cfg)
        assert result.server_port == 7777

    def test_counter_cruiser_config_env_overrides_path(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        cfg = tmp_path / 'myconfig.toml'
        cfg.write_text('[counter_cruiser]\nserver_port = 5555\n')
        monkeypatch.setenv('COUNTER_CRUISER_CONFIG', str(cfg))
        result = load_client_config()  # no explicit path → env var path
        assert result.server_port == 5555

    def test_server_config_loads(self, tmp_path: Path) -> None:
        cfg = tmp_path / 'server.toml'
        cfg.write_text('[counter_cruiser]\nport = 9000\nconfidence_threshold = 0.7\n')
        result = load_server_config(cfg)
        assert result.port == 9000
        assert result.confidence_threshold == pytest.approx(0.7)
```

- [x] **Step 6.2 — Run to confirm failures**

```bash
pytest tests/config/test_config.py -v
```

Expected: ModuleNotFoundError.

- [x] **Step 6.3 — Implement config models**

`counter_cruiser/config/models.py`:
```python
"""Pydantic-settings configuration models for client and server components."""
from __future__ import annotations

from pydantic import BaseModel, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Zone(BaseModel):
    """A named polygon zone used for elevated-dog classification."""

    id: str
    name: str
    enabled: bool = True
    polygon: list[tuple[int, int]]

    @field_validator('polygon')
    @classmethod
    def at_least_three_points(cls, v: list[tuple[int, int]]) -> list[tuple[int, int]]:
        """Reject polygons with fewer than three vertices."""
        if len(v) < 3:
            raise ValueError('polygon must have at least 3 points')
        return v


class _BaseConfig(BaseSettings):
    model_config = SettingsConfigDict(
        extra='forbid',
        env_prefix='COUNTER_CRUISER_',
    )


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

    @field_validator('jpeg_quality')
    @classmethod
    def valid_jpeg_quality(cls, v: int) -> int:
        """Enforce JPEG quality range 1–100."""
        if not 1 <= v <= 100:
            raise ValueError('jpeg_quality must be between 1 and 100')
        return v

    @field_validator('min_size_ratio')
    @classmethod
    def valid_size_ratio(cls, v: float) -> float:
        """Enforce size ratio range 0.0–1.0."""
        if not 0.0 <= v <= 1.0:
            raise ValueError('min_size_ratio must be between 0.0 and 1.0')
        return v

    @field_validator('frame_skip')
    @classmethod
    def valid_frame_skip(cls, v: int) -> int:
        """Enforce frame_skip >= 1."""
        if v < 1:
            raise ValueError('frame_skip must be >= 1')
        return v


class ServerSettings(_BaseConfig):
    """Configuration for the inference server process."""

    host: str = '0.0.0.0'
    port: int = 8765
    model_name: str = 'yolov8n.pt'
    device: str = 'auto'
    confidence_threshold: float = 0.5

    @field_validator('confidence_threshold')
    @classmethod
    def valid_confidence(cls, v: float) -> float:
        """Enforce confidence threshold range 0.0–1.0."""
        if not 0.0 <= v <= 1.0:
            raise ValueError('confidence_threshold must be between 0.0 and 1.0')
        return v
```

- [x] **Step 6.4 — Implement TOML loader**

`counter_cruiser/config/loader.py`:
```python
"""Load typed configuration from TOML files with env-var overrides."""
from __future__ import annotations

import os
import tomllib
from pathlib import Path

from counter_cruiser.config.models import ClientSettings, ServerSettings

_CONFIG_ENV_VAR = 'COUNTER_CRUISER_CONFIG'
_DEFAULT_CLIENT = Path('config/client.toml')
_DEFAULT_SERVER = Path('config/server.toml')


def _load_toml(path: Path) -> dict:
    """Read a TOML file; return empty dict if the file does not exist."""
    if not path.exists():
        return {}
    with open(path, 'rb') as fh:
        raw = tomllib.load(fh)
    # Support optional [counter_cruiser] table wrapper
    return raw.get('counter_cruiser', raw)


def _resolve_path(explicit: Path | None, default: Path) -> Path:
    """Resolve config file path: explicit > env var > default."""
    if explicit is not None:
        return explicit
    env = os.environ.get(_CONFIG_ENV_VAR)
    return Path(env) if env else default


def load_client_config(path: Path | None = None) -> ClientSettings:
    """Load and validate :class:`ClientSettings` from a TOML file.

    Resolution order: *path* argument > ``COUNTER_CRUISER_CONFIG`` env var >
    ``config/client.toml``. Missing files fall back to built-in defaults.
    Environment variables (``COUNTER_CRUISER_*``) override file values.
    """
    resolved = _resolve_path(path, _DEFAULT_CLIENT)
    data = _load_toml(resolved)
    return ClientSettings(**data)


def load_server_config(path: Path | None = None) -> ServerSettings:
    """Load and validate :class:`ServerSettings` from a TOML file.

    Same resolution order as :func:`load_client_config`.
    """
    resolved = _resolve_path(path, _DEFAULT_SERVER)
    data = _load_toml(resolved)
    return ServerSettings(**data)
```

- [x] **Step 6.5 — Create fixture TOML files**

`fixtures/client.toml`:
```toml
# Example counter-cruiser client configuration.
# Copy to config/client.toml and adjust for your setup.

[counter_cruiser]
server_host = "192.168.1.100"
server_port = 8765
camera_index = 0
frame_width = 640
frame_height = 480
jpeg_quality = 85
frame_skip = 3
min_size_ratio = 0.25

[[counter_cruiser.zones]]
id = "counter"
name = "Kitchen Counter"
enabled = true
polygon = [[100, 80], [540, 80], [540, 360], [100, 360]]
```

`fixtures/server.toml`:
```toml
# Example counter-cruiser server configuration.
# Copy to config/server.toml and adjust for your setup.

[counter_cruiser]
host = "0.0.0.0"
port = 8765
model_name = "yolov8n.pt"
device = "auto"
confidence_threshold = 0.5
```

- [x] **Step 6.6 — Run config tests**

```bash
pytest tests/config/test_config.py -v
```

Expected: all tests pass.

- [x] **Step 6.7 — Commit**

```bash
git add counter_cruiser/config/ tests/config/ fixtures/
git commit -m "feat: typed pydantic-settings config with TOML loading and env-var overrides"
```

---

## Task 7: Server — model abstraction & device selection (tasks.md 6.1–6.4)

**Files:**
- Create: `counter_cruiser/server/model.py`
- Create: `tests/server/test_model.py`

**Interfaces:**
- Consumes: `BoundingBox` from `counter_cruiser.shared.protocol`; `ServerSettings` from `counter_cruiser.config.models`
- Produces:
  - `DOG_CLASS_ID: int = 16`
  - `class DetectionModel(ABC)`: abstract `detect(frame: np.ndarray) -> list[BoundingBox]`
  - `class YOLOAdapter(DetectionModel)`: `__init__(model_name, device, confidence_threshold)`; wraps `ultralytics.YOLO`
  - `select_device(device: str) -> str`: `'auto'` → best available; explicit → passthrough

- [ ] **Step 7.1 — Write failing tests**

`tests/server/test_model.py`:
```python
"""Tests for DetectionModel abstraction and device selection."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from counter_cruiser.server.model import DOG_CLASS_ID, YOLOAdapter, select_device
from counter_cruiser.shared.protocol import BoundingBox


def _make_yolo_result(
    x1: float, y1: float, x2: float, y2: float, conf: float, cls: int
) -> MagicMock:
    """Build a fake ultralytics result object."""
    box = MagicMock()
    box.xyxy = [MagicMock(__getitem__=lambda self, i: [x1, y1, x2, y2][i])]
    box.xyxy[0].__iter__ = lambda self: iter([x1, y1, x2, y2])
    box.conf = [conf]
    box.cls = [float(cls)]
    result = MagicMock()
    result.boxes = [box]
    return result


class TestYOLOAdapter:
    @patch('counter_cruiser.server.model.YOLO')
    def test_filters_to_dog_class_only(self, mock_yolo_cls: MagicMock) -> None:
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        mock_model = MagicMock()
        mock_yolo_cls.return_value = mock_model

        # Return one dog (class 16) and one cat (class 15)
        dog_result = _make_yolo_result(10, 20, 100, 200, 0.9, DOG_CLASS_ID)
        cat_result = _make_yolo_result(200, 200, 300, 300, 0.85, 15)
        combined = MagicMock()
        combined.boxes = dog_result.boxes + cat_result.boxes
        mock_model.return_value = [combined]

        adapter = YOLOAdapter('yolov8n.pt', 'cpu', confidence_threshold=0.5)
        boxes = adapter.detect(frame)
        assert len(boxes) == 1
        assert boxes[0].class_name == 'dog'

    @patch('counter_cruiser.server.model.YOLO')
    def test_excludes_below_threshold(self, mock_yolo_cls: MagicMock) -> None:
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        mock_model = MagicMock()
        mock_yolo_cls.return_value = mock_model

        low_conf = _make_yolo_result(10, 20, 100, 200, 0.3, DOG_CLASS_ID)
        mock_model.return_value = [low_conf]

        adapter = YOLOAdapter('yolov8n.pt', 'cpu', confidence_threshold=0.5)
        boxes = adapter.detect(frame)
        assert boxes == []

    @patch('counter_cruiser.server.model.YOLO')
    def test_maps_results_to_bounding_box(self, mock_yolo_cls: MagicMock) -> None:
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        mock_model = MagicMock()
        mock_yolo_cls.return_value = mock_model

        result = _make_yolo_result(10.0, 20.0, 100.0, 200.0, 0.9, DOG_CLASS_ID)
        mock_model.return_value = [result]

        adapter = YOLOAdapter('yolov8n.pt', 'cpu', confidence_threshold=0.5)
        boxes = adapter.detect(frame)
        assert len(boxes) == 1
        b = boxes[0]
        assert isinstance(b, BoundingBox)
        assert b.x1 == 10
        assert b.y2 == 200
        assert b.class_id == DOG_CLASS_ID


class TestSelectDevice:
    def test_explicit_device_returned_unchanged(self) -> None:
        assert select_device('cpu') == 'cpu'
        assert select_device('cuda:0') == 'cuda:0'
        assert select_device('mps') == 'mps'

    @patch('counter_cruiser.server.model.torch')
    def test_auto_picks_cuda_when_available(self, mock_torch: MagicMock) -> None:
        mock_torch.cuda.is_available.return_value = True
        assert select_device('auto') == 'cuda:0'

    @patch('counter_cruiser.server.model.torch')
    def test_auto_picks_mps_when_no_cuda(self, mock_torch: MagicMock) -> None:
        mock_torch.cuda.is_available.return_value = False
        mock_torch.backends.mps.is_available.return_value = True
        assert select_device('auto') == 'mps'

    @patch('counter_cruiser.server.model.torch')
    def test_auto_falls_back_to_cpu(self, mock_torch: MagicMock) -> None:
        mock_torch.cuda.is_available.return_value = False
        mock_torch.backends.mps.is_available.return_value = False
        assert select_device('auto') == 'cpu'
```

- [ ] **Step 7.2 — Run to confirm failures**

```bash
pytest tests/server/test_model.py -v
```

Expected: ModuleNotFoundError.

- [ ] **Step 7.3 — Implement model.py**

`counter_cruiser/server/model.py`:
```python
"""Detection model abstraction and device selection for the inference server."""
from __future__ import annotations

from abc import ABC, abstractmethod

import numpy as np

from counter_cruiser.shared.protocol import BoundingBox

DOG_CLASS_ID = 16  # COCO dataset index for "dog"

# Imported at module level so tests can patch it without importing torch/ultralytics
try:
    import torch
    from ultralytics import YOLO
except ImportError:  # pragma: no cover
    torch = None  # type: ignore[assignment]
    YOLO = None  # type: ignore[assignment]


class DetectionModel(ABC):
    """Abstract base for pluggable detection models."""

    @abstractmethod
    def detect(self, frame: np.ndarray) -> list[BoundingBox]:
        """Run inference on *frame*; return dog detections above threshold."""


class YOLOAdapter(DetectionModel):
    """Wraps an ``ultralytics.YOLO`` model, filtering to dogs above threshold."""

    def __init__(self, model_name: str, device: str, confidence_threshold: float) -> None:
        """Load the YOLO model once at construction time."""
        self._model = YOLO(model_name)
        self._device = device
        self._threshold = confidence_threshold

    def detect(self, frame: np.ndarray) -> list[BoundingBox]:
        """Return dog :class:`BoundingBox` objects for detections above threshold."""
        results = self._model(frame, device=self._device, verbose=False)
        boxes: list[BoundingBox] = []
        for result in results:
            for box in result.boxes:
                cls_id = int(box.cls[0])
                conf = float(box.conf[0])
                if cls_id != DOG_CLASS_ID or conf < self._threshold:
                    continue
                x1, y1, x2, y2 = (int(v) for v in box.xyxy[0])
                boxes.append(
                    BoundingBox(
                        x1=x1, y1=y1, x2=x2, y2=y2,
                        confidence=conf, class_id=cls_id, class_name='dog',
                    )
                )
        return boxes


def select_device(device: str) -> str:
    """Resolve the compute device string.

    ``'auto'`` selects CUDA if available, then MPS, then CPU.
    Any other value is returned unchanged.
    """
    if device != 'auto':
        return device
    if torch is not None:
        if torch.cuda.is_available():
            return 'cuda:0'
        if hasattr(torch.backends, 'mps') and torch.backends.mps.is_available():
            return 'mps'
    return 'cpu'
```

- [ ] **Step 7.4 — Run server model tests**

```bash
pytest tests/server/test_model.py -v
```

Expected: all tests pass.

- [ ] **Step 7.5 — Commit**

```bash
git add counter_cruiser/server/model.py tests/server/test_model.py
git commit -m "feat: DetectionModel ABC, YOLOAdapter, and auto device selection"
```

---

## Task 8: Server — WebSocket handler & entrypoint (tasks.md 7.1–7.3)

**Files:**
- Create: `counter_cruiser/server/handler.py`
- Create: `counter_cruiser/server/__main__.py`
- Create: `tests/server/test_handler.py`

**Interfaces:**
- Consumes: `handle_connection(websocket, model: DetectionModel) -> None`; uses `deserialize`, `serialize`, `decode_frame`, `make_error`, `make_pong`, `DetectionMessage`
- Produces: `handle_connection` coroutine; `main()` server entrypoint

- [ ] **Step 8.1 — Write failing handler tests**

`tests/server/test_handler.py`:
```python
"""Tests for the WebSocket connection handler."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np
import pytest

from counter_cruiser.server.handler import handle_connection
from counter_cruiser.server.model import DetectionModel
from counter_cruiser.shared.protocol import (
    BoundingBox,
    DetectionMessage,
    FrameMessage,
    PingMessage,
    encode_frame,
    make_pong,
    serialize,
)


class FakeModel(DetectionModel):
    def __init__(self, boxes: list[BoundingBox] | None = None) -> None:
        self._boxes = boxes or []

    def detect(self, frame: np.ndarray) -> list[BoundingBox]:
        return self._boxes


def _fake_ws(messages: list[str]) -> MagicMock:
    """Build a mock websocket that yields *messages* then stops."""
    ws = MagicMock()
    ws.remote_address = ('127.0.0.1', 12345)
    ws.__aiter__ = MagicMock(return_value=aiter_from(messages))
    ws.send = AsyncMock()
    return ws


def aiter_from(items: list):
    """Async iterator over *items*."""
    async def _gen():
        for item in items:
            yield item
    return _gen()


class TestHandleConnection:
    async def test_valid_frame_returns_detection(self, sample_frame: np.ndarray) -> None:
        box = BoundingBox(x1=0, y1=0, x2=50, y2=100, confidence=0.9, class_id=16, class_name='dog')
        model = FakeModel([box])
        frame_msg = encode_frame(sample_frame, frame_id=1, quality=85)
        ws = _fake_ws([serialize(frame_msg)])

        await handle_connection(ws, model)

        ws.send.assert_called_once()
        sent = json.loads(ws.send.call_args[0][0])
        assert sent['type'] == 'detection'
        assert sent['frame_id'] == 1
        assert len(sent['boxes']) == 1

    async def test_ping_is_answered_with_pong(self) -> None:
        ping = PingMessage()
        ws = _fake_ws([serialize(ping)])
        await handle_connection(ws, FakeModel())

        ws.send.assert_called_once()
        sent = json.loads(ws.send.call_args[0][0])
        assert sent['type'] == 'pong'
        assert sent['ping_timestamp'] == ping.timestamp.isoformat()

    async def test_processing_error_sends_error_message_and_continues(
        self, sample_frame: np.ndarray
    ) -> None:
        class BrokenModel(DetectionModel):
            def detect(self, frame: np.ndarray) -> list[BoundingBox]:
                raise RuntimeError('GPU exploded')

        frame_msg = encode_frame(sample_frame, frame_id=5, quality=85)
        ws = _fake_ws([serialize(frame_msg)])
        await handle_connection(ws, BrokenModel())

        ws.send.assert_called_once()
        sent = json.loads(ws.send.call_args[0][0])
        assert sent['type'] == 'error'
        assert sent['frame_id'] == 5

    async def test_multiple_frames_processed_independently(
        self, sample_frame: np.ndarray
    ) -> None:
        model = FakeModel()
        frames = [serialize(encode_frame(sample_frame, i, 85)) for i in range(3)]
        ws = _fake_ws(frames)
        await handle_connection(ws, model)
        assert ws.send.call_count == 3
```

- [ ] **Step 8.2 — Run to confirm failures**

```bash
pytest tests/server/test_handler.py -v
```

Expected: ModuleNotFoundError.

- [ ] **Step 8.3 — Implement handler.py**

`counter_cruiser/server/handler.py`:
```python
"""WebSocket connection handler for the inference server."""
from __future__ import annotations

import logging
import time

import websockets.exceptions

from counter_cruiser.server.model import DetectionModel
from counter_cruiser.shared.protocol import (
    DetectionMessage,
    FrameMessage,
    PingMessage,
    decode_frame,
    deserialize,
    make_error,
    make_pong,
    serialize,
)

logger = logging.getLogger(__name__)


async def handle_connection(websocket, model: DetectionModel) -> None:
    """Handle a single client connection; process frames until the client disconnects."""
    logger.info('Client connected: %s', websocket.remote_address)
    try:
        async for raw in websocket:
            msg = None
            try:
                msg = deserialize(raw)
                if isinstance(msg, PingMessage):
                    await websocket.send(serialize(make_pong(msg)))
                elif isinstance(msg, FrameMessage):
                    t0 = time.perf_counter()
                    frame, frame_id = decode_frame(msg)
                    boxes = model.detect(frame)
                    elapsed_ms = (time.perf_counter() - t0) * 1000.0
                    result = DetectionMessage(
                        frame_id=frame_id, boxes=boxes, processing_time_ms=elapsed_ms
                    )
                    await websocket.send(serialize(result))
            except Exception as exc:
                logger.exception('Error processing message: %s', exc)
                frame_id = msg.frame_id if isinstance(msg, FrameMessage) else None
                await websocket.send(serialize(make_error('processing_error', str(exc), frame_id)))
    except websockets.exceptions.ConnectionClosed:
        logger.info('Client disconnected: %s', websocket.remote_address)
```

- [ ] **Step 8.4 — Implement server entrypoint**

`counter_cruiser/server/__main__.py`:
```python
"""Server entrypoint: load config, model, and start the WebSocket server."""
from __future__ import annotations

import asyncio
import logging

import websockets

from counter_cruiser.config.loader import load_server_config
from counter_cruiser.server.handler import handle_connection
from counter_cruiser.server.model import YOLOAdapter, select_device

logger = logging.getLogger(__name__)


def _configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s %(name)s %(levelname)s %(message)s',
    )


async def _serve() -> None:
    """Load config and model, then serve indefinitely."""
    config = load_server_config()
    device = select_device(config.device)
    logger.info('Loading model %s on device %s', config.model_name, device)
    model = YOLOAdapter(config.model_name, device, config.confidence_threshold)
    logger.info('Server listening on %s:%d', config.host, config.port)
    async with websockets.serve(
        lambda ws: handle_connection(ws, model),
        config.host,
        config.port,
    ):
        await asyncio.Future()  # run until cancelled  # pragma: no cover


def main() -> None:
    """Configure logging and run the server."""
    _configure_logging()
    asyncio.run(_serve())


if __name__ == '__main__':  # pragma: no cover
    main()
```

- [ ] **Step 8.5 — Run handler tests**

```bash
pytest tests/server/ -v
```

Expected: all tests pass.

- [ ] **Step 8.6 — Commit**

```bash
git add counter_cruiser/server/handler.py counter_cruiser/server/__main__.py tests/server/test_handler.py
git commit -m "feat: websocket connection handler and server entrypoint"
```

---

## Task 9: Client — camera capture & frame skipping (tasks.md 8.1–8.4)

**Files:**
- Create: `counter_cruiser/client/capture.py`
- Create: `tests/client/test_capture.py`

**Interfaces:**
- Produces:
  - `CameraCapture(Protocol)`: `open(index, width, height) -> tuple[int, int]`, `read() -> np.ndarray | None`, `release() -> None`
  - `OpenCVCapture(CameraCapture)`: real implementation via `cv2.VideoCapture`

- [ ] **Step 9.1 — Write failing camera tests**

`tests/client/test_capture.py`:
```python
"""Tests for camera capture interface and OpenCV implementation."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from counter_cruiser.client.capture import OpenCVCapture


class TestOpenCVCapture:
    @patch('counter_cruiser.client.capture.cv2')
    def test_open_succeeds_and_returns_actual_dims(self, mock_cv2: MagicMock) -> None:
        cap_mock = MagicMock()
        cap_mock.isOpened.return_value = True
        cap_mock.get.side_effect = lambda prop: {3: 640.0, 4: 480.0}.get(prop, 0.0)
        mock_cv2.VideoCapture.return_value = cap_mock
        mock_cv2.CAP_PROP_FRAME_WIDTH = 3
        mock_cv2.CAP_PROP_FRAME_HEIGHT = 4

        capture = OpenCVCapture()
        w, h = capture.open(index=0, width=640, height=480)

        assert w == 640
        assert h == 480
        cap_mock.set.assert_any_call(3, 640)
        cap_mock.set.assert_any_call(4, 480)

    @patch('counter_cruiser.client.capture.cv2')
    def test_open_failure_raises_runtime_error(self, mock_cv2: MagicMock) -> None:
        cap_mock = MagicMock()
        cap_mock.isOpened.return_value = False
        mock_cv2.VideoCapture.return_value = cap_mock

        capture = OpenCVCapture()
        with pytest.raises(RuntimeError, match='Cannot open camera'):
            capture.open(index=99, width=640, height=480)

    @patch('counter_cruiser.client.capture.cv2')
    def test_read_returns_frame_on_success(self, mock_cv2: MagicMock) -> None:
        cap_mock = MagicMock()
        cap_mock.isOpened.return_value = True
        cap_mock.get.return_value = 640.0
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        cap_mock.read.return_value = (True, frame)
        mock_cv2.VideoCapture.return_value = cap_mock
        mock_cv2.CAP_PROP_FRAME_WIDTH = 3
        mock_cv2.CAP_PROP_FRAME_HEIGHT = 4

        capture = OpenCVCapture()
        capture.open(0, 640, 480)
        result = capture.read()

        assert result is not None
        assert result.shape == (480, 640, 3)

    @patch('counter_cruiser.client.capture.cv2')
    def test_transient_read_failure_returns_none(self, mock_cv2: MagicMock) -> None:
        cap_mock = MagicMock()
        cap_mock.isOpened.return_value = True
        cap_mock.get.return_value = 640.0
        cap_mock.read.return_value = (False, None)
        mock_cv2.VideoCapture.return_value = cap_mock
        mock_cv2.CAP_PROP_FRAME_WIDTH = 3
        mock_cv2.CAP_PROP_FRAME_HEIGHT = 4

        capture = OpenCVCapture()
        capture.open(0, 640, 480)
        assert capture.read() is None

    @patch('counter_cruiser.client.capture.cv2')
    def test_release_closes_camera(self, mock_cv2: MagicMock) -> None:
        cap_mock = MagicMock()
        cap_mock.isOpened.return_value = True
        cap_mock.get.return_value = 640.0
        mock_cv2.VideoCapture.return_value = cap_mock
        mock_cv2.CAP_PROP_FRAME_WIDTH = 3
        mock_cv2.CAP_PROP_FRAME_HEIGHT = 4

        capture = OpenCVCapture()
        capture.open(0, 640, 480)
        capture.release()
        cap_mock.release.assert_called_once()
```

- [ ] **Step 9.2 — Run to confirm failures**

```bash
pytest tests/client/test_capture.py -v
```

Expected: ModuleNotFoundError.

- [ ] **Step 9.3 — Implement capture.py**

`counter_cruiser/client/capture.py`:
```python
"""Camera capture interface and OpenCV implementation."""
from __future__ import annotations

import logging
from typing import Protocol

import cv2
import numpy as np

logger = logging.getLogger(__name__)


class CameraCapture(Protocol):
    """Protocol for camera frame sources; injectable for testing."""

    def open(self, index: int, width: int, height: int) -> tuple[int, int]:
        """Open the camera and configure resolution; return actual (width, height)."""
        ...

    def read(self) -> np.ndarray | None:
        """Read and return the next frame, or None on transient failure."""
        ...

    def release(self) -> None:
        """Release the camera resource."""
        ...


class OpenCVCapture:
    """Real camera implementation backed by ``cv2.VideoCapture``."""

    def __init__(self) -> None:
        """Create an unopened capture instance."""
        self._cap: cv2.VideoCapture | None = None

    def open(self, index: int, width: int, height: int) -> tuple[int, int]:
        """Open camera at *index*, set requested resolution, return actual (w, h).

        Raises ``RuntimeError`` if the camera cannot be opened.
        """
        cap = cv2.VideoCapture(index)
        if not cap.isOpened():
            raise RuntimeError(f'Cannot open camera at index {index}')
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
        self._cap = cap
        actual_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        actual_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        logger.info('Camera %d opened at %dx%d', index, actual_w, actual_h)
        return actual_w, actual_h

    def read(self) -> np.ndarray | None:
        """Return the next BGR frame, or None if the read failed."""
        if self._cap is None:
            return None
        ok, frame = self._cap.read()
        return frame if ok else None

    def release(self) -> None:
        """Release the underlying VideoCapture."""
        if self._cap is not None:
            self._cap.release()
            self._cap = None
```

- [ ] **Step 9.4 — Run camera tests**

```bash
pytest tests/client/test_capture.py -v
```

Expected: all tests pass.

- [ ] **Step 9.5 — Commit**

```bash
git add counter_cruiser/client/capture.py tests/client/test_capture.py
git commit -m "feat: CameraCapture protocol and OpenCV implementation"
```

---

## Task 10: Client — transport, resilience & entrypoint (tasks.md 9.1–9.5)

**Files:**
- Create: `counter_cruiser/client/transport.py`
- Create: `counter_cruiser/client/__main__.py`
- Create: `tests/client/test_transport.py`

**Interfaces:**
- Consumes: `CameraCapture`, `ClientSettings`, `encode_frame`, `serialize`, `deserialize`, `DetectionMessage`, `ErrorMessage`
- Produces:
  - `class ClientSession`: `__init__(capture, config, on_result, reconnect_interval=5.0)`, `async run() -> None`, `stop() -> None`
  - `on_result` type: `Callable[[DetectionMessage, float], None]`

- [ ] **Step 10.1 — Write failing transport tests**

`tests/client/test_transport.py`:
```python
"""Tests for ClientSession: frame send/receive, frame skipping, resilience."""
from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np
import pytest

from counter_cruiser.client.transport import ClientSession
from counter_cruiser.config.models import ClientSettings
from counter_cruiser.shared.protocol import (
    BoundingBox,
    DetectionMessage,
    ErrorMessage,
    FrameMessage,
    encode_frame,
    serialize,
)


class FakeCapture:
    """Camera fake: yields *frames* in order, then returns None indefinitely."""

    def __init__(self, frames: list[np.ndarray]) -> None:
        self._frames = iter(frames)
        self.released = False

    def open(self, index: int, width: int, height: int) -> tuple[int, int]:
        return (640, 480)

    def read(self) -> np.ndarray | None:
        return next(self._frames, None)

    def release(self) -> None:
        self.released = True


def _blank_frame() -> np.ndarray:
    return np.zeros((480, 640, 3), dtype=np.uint8)


def _default_config(**overrides) -> ClientSettings:
    return ClientSettings(frame_skip=1, jpeg_quality=85, **overrides)


class TestClientSessionSendReceive:
    async def test_frame_sent_and_detection_matched(self) -> None:
        """Session sends a frame; when detection comes back it calls on_result."""
        results: list[tuple[DetectionMessage, float]] = []

        capture = FakeCapture([_blank_frame()])
        config = _default_config()

        detection_payload = None

        async def fake_connect(url, **kw):
            class FakeWS:
                async def send(self, data: str) -> None:
                    nonlocal detection_payload
                    msg = json.loads(data)
                    # Echo back a detection for the frame id
                    detection_payload = serialize(
                        DetectionMessage(frame_id=msg['frame_id'], boxes=[], processing_time_ms=1.0)
                    )

                def __aiter__(self):
                    return self._iter()

                async def _iter(self):
                    # Wait until detection_payload is set then yield it
                    while detection_payload is None:
                        await asyncio.sleep(0.001)
                    yield detection_payload

                async def close(self):
                    pass

                async def __aenter__(self):
                    return self

                async def __aexit__(self, *_):
                    pass

            return FakeWS()

        session = ClientSession(
            capture=capture,
            config=config,
            on_result=lambda m, l: results.append((m, l)),
            reconnect_interval=0.01,
        )

        with patch('counter_cruiser.client.transport.websockets.connect', side_effect=fake_connect):
            task = asyncio.create_task(session.run())
            deadline = asyncio.get_event_loop().time() + 3.0
            while not results and asyncio.get_event_loop().time() < deadline:
                await asyncio.sleep(0.01)
            session.stop()
            await asyncio.wait_for(task, timeout=2.0)

        assert len(results) >= 1
        assert results[0][1] >= 0.0  # latency non-negative

    async def test_frame_skip_sends_every_nth_frame(self) -> None:
        """With frame_skip=3, only 1 in 3 frames is sent."""
        sent_count = 0

        capture = FakeCapture([_blank_frame()] * 9)
        config = _default_config(frame_skip=3)

        class FakeWS:
            async def send(self, data: str) -> None:
                nonlocal sent_count
                if json.loads(data).get('type') == 'frame':
                    sent_count += 1

            def __aiter__(self):
                return self._iter()

            async def _iter(self):
                # Yield nothing; the send loop drains naturally when camera returns None
                if False:
                    yield  # make this an async generator

            async def close(self): pass
            async def __aenter__(self): return self
            async def __aexit__(self, *_): pass

        async def fake_connect(url, **kw):
            return FakeWS()

        session = ClientSession(
            capture=capture, config=config,
            on_result=lambda m, l: None,
            reconnect_interval=0.01,
        )

        with patch('counter_cruiser.client.transport.websockets.connect', side_effect=fake_connect):
            task = asyncio.create_task(session.run())
            await asyncio.sleep(0.2)
            session.stop()
            try:
                await asyncio.wait_for(task, timeout=2.0)
            except Exception:
                pass

        assert sent_count == 3  # 9 frames / skip=3

    async def test_server_error_message_is_logged(self, caplog) -> None:
        import logging
        capture = FakeCapture([])
        config = _default_config()

        error_msg = serialize(ErrorMessage(error_type='oops', message='bad things'))

        class FakeWS:
            async def send(self, data: str) -> None: pass
            def __aiter__(self): return self._iter()
            async def _iter(self):
                yield error_msg
            async def close(self): pass
            async def __aenter__(self): return self
            async def __aexit__(self, *_): pass

        async def fake_connect(url, **kw):
            return FakeWS()

        session = ClientSession(
            capture=capture, config=config,
            on_result=lambda m, l: None,
            reconnect_interval=0.01,
        )
        with caplog.at_level(logging.ERROR, logger='counter_cruiser.client.transport'):
            with patch('counter_cruiser.client.transport.websockets.connect', side_effect=fake_connect):
                task = asyncio.create_task(session.run())
                await asyncio.sleep(0.1)
                session.stop()
                try:
                    await asyncio.wait_for(task, timeout=2.0)
                except Exception:
                    pass

        assert any('oops' in r.message for r in caplog.records)

    async def test_camera_released_on_stop(self) -> None:
        capture = FakeCapture([])
        config = _default_config()

        async def fake_connect(url, **kw):
            raise OSError('refused')

        session = ClientSession(
            capture=capture, config=config,
            on_result=lambda m, l: None,
            reconnect_interval=0.01,
        )
        with patch('counter_cruiser.client.transport.websockets.connect', side_effect=fake_connect):
            task = asyncio.create_task(session.run())
            await asyncio.sleep(0.05)
            session.stop()
            await asyncio.wait_for(task, timeout=2.0)

        assert capture.released is True
```

- [ ] **Step 10.2 — Run to confirm failures**

```bash
pytest tests/client/test_transport.py -v
```

Expected: ModuleNotFoundError.

- [ ] **Step 10.3 — Implement transport.py**

`counter_cruiser/client/transport.py`:
```python
"""WebSocket client session: send frames, receive detections, reconnect on drop."""
from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Callable

import websockets
import websockets.exceptions

from counter_cruiser.client.capture import CameraCapture
from counter_cruiser.config.models import ClientSettings
from counter_cruiser.shared.protocol import (
    DetectionMessage,
    ErrorMessage,
    FrameMessage,
    deserialize,
    encode_frame,
    serialize,
)

logger = logging.getLogger(__name__)


class ClientSession:
    """Manages the camera→server→zone-analysis pipeline with auto-reconnect.

    Constructs with injected dependencies so every part is testable headlessly.
    """

    def __init__(
        self,
        capture: CameraCapture,
        config: ClientSettings,
        on_result: Callable[[DetectionMessage, float], None],
        reconnect_interval: float = 5.0,
    ) -> None:
        """Initialise the session without opening any resources."""
        self._capture = capture
        self._config = config
        self._on_result = on_result
        self._reconnect_interval = reconnect_interval
        self._running = True
        self._pending: dict[int, float] = {}
        self._frame_id = 0

    @property
    def _url(self) -> str:
        return f'ws://{self._config.server_host}:{self._config.server_port}'

    async def run(self) -> None:
        """Open the camera, connect to the server, and run until stopped."""
        self._capture.open(
            self._config.camera_index,
            self._config.frame_width,
            self._config.frame_height,
        )
        try:
            while self._running:
                try:
                    async with websockets.connect(self._url) as ws:
                        await self._run_connection(ws)
                except (OSError, websockets.exceptions.WebSocketException) as exc:
                    if not self._running:
                        break
                    logger.warning(
                        'Connection to %s failed: %s — retrying in %.1fs',
                        self._url, exc, self._reconnect_interval,
                    )
                    await asyncio.sleep(self._reconnect_interval)
        finally:
            self._capture.release()

    async def _run_connection(self, ws) -> None:
        """Run send and receive loops concurrently; raise on first exception."""
        self._pending.clear()
        send_task = asyncio.create_task(self._send_loop(ws))
        recv_task = asyncio.create_task(self._receive_loop(ws))
        try:
            await asyncio.gather(send_task, recv_task)
        except Exception:
            send_task.cancel()
            recv_task.cancel()
            await asyncio.gather(send_task, recv_task, return_exceptions=True)
            raise

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
            msg = encode_frame(frame, self._frame_id, self._config.jpeg_quality)
            self._pending[self._frame_id] = time.monotonic()
            await ws.send(serialize(msg))
        await ws.close()

    async def _receive_loop(self, ws) -> None:
        """Receive detections and errors; match detections to sent frames."""
        async for raw in ws:
            msg = deserialize(raw)
            if isinstance(msg, DetectionMessage):
                sent_at = self._pending.pop(msg.frame_id, None)
                latency = (time.monotonic() - sent_at) if sent_at is not None else 0.0
                self._on_result(msg, latency)
            elif isinstance(msg, ErrorMessage):
                logger.error(
                    'Server error [%s]: %s (frame=%s)',
                    msg.error_type, msg.message, msg.frame_id,
                )

    def stop(self) -> None:
        """Signal the session to stop sending and exit after the current frame."""
        self._running = False
```

- [ ] **Step 10.4 — Implement client entrypoint**

`counter_cruiser/client/__main__.py`:
```python
"""Client entrypoint: wire config, camera, transport, zone analysis, and debounce."""
from __future__ import annotations

import asyncio
import logging
import signal

from counter_cruiser.client.capture import OpenCVCapture
from counter_cruiser.client.transport import ClientSession
from counter_cruiser.config.loader import load_client_config
from counter_cruiser.shared.debounce import DetectionHistory
from counter_cruiser.shared.geometry import analyze_detections
from counter_cruiser.shared.protocol import DetectionMessage

logger = logging.getLogger(__name__)


def _configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s %(name)s %(levelname)s %(message)s',
    )


def main() -> None:
    """Load configuration and run the client until interrupted."""
    _configure_logging()
    config = load_client_config()
    history = DetectionHistory()

    def on_result(msg: DetectionMessage, latency: float) -> None:
        analysis = analyze_detections(
            msg.boxes, config.zones, config.frame_height, config.min_size_ratio
        )
        history.add(msg.frame_id, analysis.elevated)
        actionable = history.is_consecutive_elevated()
        status = 'ELEVATED' if actionable else 'floor'
        zones = ', '.join(sorted(analysis.triggered_zones)) if analysis.triggered_zones else 'none'
        logger.info(
            'frame=%d latency=%.1fms status=%s zones=[%s]',
            msg.frame_id, latency * 1000.0, status, zones,
        )

    session = ClientSession(
        capture=OpenCVCapture(), config=config, on_result=on_result
    )

    def _shutdown(signum, frame):  # pragma: no cover
        logger.info('Shutdown signal received')
        session.stop()

    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    asyncio.run(session.run())


if __name__ == '__main__':  # pragma: no cover
    main()
```

- [ ] **Step 10.5 — Run transport tests**

```bash
pytest tests/client/ -v
```

Expected: all tests pass.

- [ ] **Step 10.6 — Commit**

```bash
git add counter_cruiser/client/transport.py counter_cruiser/client/__main__.py tests/client/test_transport.py
git commit -m "feat: ClientSession with send/receive loops, frame skipping, and reconnect supervisor"
```

---

## Task 11: End-to-end pipeline reporting (tasks.md 10.1–10.2)

**Files:**
- Create: `tests/test_integration.py`

**Interfaces:**
- Consumes: all previously built components
- Produces: integration test asserting elevated and floor dogs are correctly reported via the real pipeline (mocked camera + in-process WebSocket server + fake model)

- [ ] **Step 11.1 — Write the integration test**

`tests/test_integration.py`:
```python
"""Integration tests: fake camera + in-process WebSocket + fake model → console report."""
from __future__ import annotations

import asyncio
import logging

import numpy as np
import pytest
import websockets

from counter_cruiser.client.transport import ClientSession
from counter_cruiser.config.models import ClientSettings, Zone
from counter_cruiser.server.handler import handle_connection
from counter_cruiser.server.model import DetectionModel
from counter_cruiser.shared.debounce import DetectionHistory
from counter_cruiser.shared.geometry import analyze_detections
from counter_cruiser.shared.protocol import BoundingBox, DetectionMessage


class _FakeCapture:
    """Yields *frames* in order; returns None once exhausted."""

    def __init__(self, frames: list[np.ndarray]) -> None:
        self._frames = list(frames)
        self._idx = 0
        self.released = False

    def open(self, index: int, width: int, height: int) -> tuple[int, int]:
        return (640, 480)

    def read(self) -> np.ndarray | None:
        if self._idx >= len(self._frames):
            return None
        frame = self._frames[self._idx]
        self._idx += 1
        return frame

    def release(self) -> None:
        self.released = True


class _FakeModel(DetectionModel):
    def __init__(self, boxes: list[BoundingBox]) -> None:
        self._boxes = boxes

    def detect(self, frame: np.ndarray) -> list[BoundingBox]:
        return self._boxes


@pytest.mark.integration
async def test_elevated_dog_reported(caplog) -> None:
    """Elevated dog → pipeline logs ELEVATED status after two consecutive frames."""
    zone = Zone(
        id='counter', name='Counter', enabled=True,
        polygon=[(0, 0), (640, 0), (640, 480), (0, 480)],
    )
    # Box height=300, frame_height=480 → ratio≈0.625 > min_size_ratio=0.25; inside zone
    elevated_box = BoundingBox(
        x1=0, y1=0, x2=100, y2=300, confidence=0.9, class_id=16, class_name='dog'
    )
    frames = [np.zeros((480, 640, 3), dtype=np.uint8)] * 4
    config = ClientSettings(
        server_host='localhost',
        server_port=0,  # overridden below
        zones=[zone],
        min_size_ratio=0.25,
        frame_skip=1,
        jpeg_quality=85,
    )

    received: list[tuple[DetectionMessage, float]] = []
    history = DetectionHistory()
    statuses: list[str] = []

    def on_result(msg: DetectionMessage, latency: float) -> None:
        received.append((msg, latency))
        analysis = analyze_detections(msg.boxes, config.zones, 480, config.min_size_ratio)
        history.add(msg.frame_id, analysis.elevated)
        statuses.append('ELEVATED' if history.is_consecutive_elevated() else 'floor')

    async with websockets.serve(
        lambda ws: handle_connection(ws, _FakeModel([elevated_box])),
        'localhost', 0,
    ) as server:
        port = server.sockets[0].getsockname()[1]
        config = ClientSettings(
            server_host='localhost', server_port=port,
            zones=[zone], min_size_ratio=0.25, frame_skip=1, jpeg_quality=85,
        )
        capture = _FakeCapture(frames)
        session = ClientSession(capture=capture, config=config, on_result=on_result, reconnect_interval=0.1)

        task = asyncio.create_task(session.run())
        deadline = asyncio.get_event_loop().time() + 5.0
        while len(received) < 2 and asyncio.get_event_loop().time() < deadline:
            await asyncio.sleep(0.02)
        session.stop()
        await asyncio.wait_for(task, timeout=3.0)

    assert len(received) >= 2
    assert received[0][0].boxes[0].class_name == 'dog'
    # After two consecutive elevated frames the status flips to ELEVATED
    assert 'ELEVATED' in statuses


@pytest.mark.integration
async def test_floor_dog_reported_not_elevated() -> None:
    """Small dog below min_size_ratio is reported as floor (not elevated)."""
    zone = Zone(
        id='counter', name='Counter', enabled=True,
        polygon=[(0, 0), (640, 0), (640, 480), (0, 480)],
    )
    # Box height=50, frame_height=480 → ratio≈0.10 < min_size_ratio=0.25 → floor
    floor_box = BoundingBox(
        x1=0, y1=0, x2=100, y2=50, confidence=0.9, class_id=16, class_name='dog'
    )
    frames = [np.zeros((480, 640, 3), dtype=np.uint8)] * 3
    history = DetectionHistory()
    statuses: list[str] = []

    def on_result(msg: DetectionMessage, latency: float) -> None:
        analysis = analyze_detections(msg.boxes, [zone], 480, 0.25)
        history.add(msg.frame_id, analysis.elevated)
        statuses.append('ELEVATED' if history.is_consecutive_elevated() else 'floor')

    async with websockets.serve(
        lambda ws: handle_connection(ws, _FakeModel([floor_box])),
        'localhost', 0,
    ) as server:
        port = server.sockets[0].getsockname()[1]
        config = ClientSettings(
            server_host='localhost', server_port=port,
            zones=[zone], min_size_ratio=0.25, frame_skip=1, jpeg_quality=85,
        )
        capture = _FakeCapture(frames)
        session = ClientSession(capture=capture, config=config, on_result=on_result, reconnect_interval=0.1)

        task = asyncio.create_task(session.run())
        deadline = asyncio.get_event_loop().time() + 5.0
        while len(statuses) < 2 and asyncio.get_event_loop().time() < deadline:
            await asyncio.sleep(0.02)
        session.stop()
        await asyncio.wait_for(task, timeout=3.0)

    assert len(statuses) >= 1
    assert all(s == 'floor' for s in statuses)
```

- [ ] **Step 11.2 — Run integration tests**

```bash
pytest tests/test_integration.py -v -m integration
```

Expected: both tests pass.

- [ ] **Step 11.3 — Commit**

```bash
git add tests/test_integration.py
git commit -m "test: integration tests for elevated and floor dog pipeline reporting"
```

---

## Task 12: Finalization (tasks.md 11.1–11.4)

**Files:**
- Modify: `CLAUDE.md` (Architecture/Commands sections)

- [ ] **Step 12.1 — Run full test suite with coverage**

```bash
pytest --cov=counter_cruiser --cov-report=term-missing --cov-fail-under=100
```

Expected: all tests pass, coverage at 100%. If any line is missed, either add a test or add `# pragma: no cover` with justification in a comment.

- [ ] **Step 12.2 — Run ruff lint**

```bash
ruff check .
```

Expected: exits 0 with no findings. Fix any violations; do not suppress without justification.

- [ ] **Step 12.3 — Run ruff formatter check**

```bash
ruff format --check .
```

Expected: exits 0. If not, run `ruff format .` and re-check.

- [ ] **Step 12.4 — Verify docstrings on all public symbols**

```bash
ruff check --select D .
```

If `D` rules are not in the project config, manually verify: every public module, class, and function has at least a one-line docstring. Private helpers (leading `_`) are exempt.

- [ ] **Step 12.5 — Update CLAUDE.md architecture section**

In `CLAUDE.md`, update (or create) an Architecture section reflecting the real layout:

```markdown
## Architecture

Single `counter_cruiser` package installed via `uv`. Sub-packages:
- `shared/`: `geometry.py` (containment + elevated decision), `debounce.py` (consecutive detection), `protocol.py` (Pydantic message models + codec)
- `config/`: `models.py` (Zone, ClientSettings, ServerSettings), `loader.py` (TOML + env)
- `client/`: `capture.py` (CameraCapture protocol + OpenCV impl), `transport.py` (ClientSession), `__main__.py` (entrypoint)
- `server/`: `model.py` (DetectionModel ABC + YOLOAdapter), `handler.py` (WebSocket handler), `__main__.py` (entrypoint)

Zone analysis lives on the client. The server is a stateless inference service.

## Commands

```bash
# Install (editable, with dev extras)
uv pip install -e ".[dev]"

# Run tests with coverage
pytest

# Lint
ruff check .

# Format
ruff format .

# Run server (requires server extra)
uv pip install -e ".[server]"
python -m counter_cruiser.server

# Run client
python -m counter_cruiser.client
```
```

- [ ] **Step 12.6 — Final commit**

```bash
git add CLAUDE.md
git commit -m "docs: update CLAUDE.md architecture and commands for foundation release"
```

---

## Self-Review Checklist

### Spec coverage

| Spec requirement | Covered by |
|---|---|
| File-based config loading | Task 6 (loader.py, TestTomlLoading) |
| TOML + env-var precedence | Task 6 (TestTomlLoading.test_env_var_overrides) |
| Unknown config key rejected | Task 6 (test_unknown_key_rejected) |
| Zone polygon ≥3 points | Task 6 (TestZoneModel) |
| Typed message models + discriminator | Task 5 (TestMessageModels) |
| Message timestamp | Task 5 (test_all_messages_carry_timestamp) |
| Round-trip serialization | Task 5 (TestSerializeDeserialize) |
| Malformed/unknown type rejected | Task 5 (test_malformed_json_raises, test_unknown_type_raises) |
| Frame encode → image+id+shape+timestamp | Task 5 (TestFrameCodec) |
| Frame decode recovers equivalent image | Task 5 (test_decode_recovers_compatible_frame) |
| Encode failure raises | Task 5 (test_encode_failure_raises) |
| Error message carries context + frame_id | Task 5 (TestErrorAndPingPong) |
| Ping answered with pong echoing timestamp | Tasks 5 + 8 |
| Point-in-polygon containment (5 test points) | Task 2 |
| Disabled zones ignored | Task 2 |
| Large+in-zone → elevated | Task 3 |
| Size ratio = box_height / frame_height | Task 3 |
| Any elevated marks frame elevated | Task 3 |
| Triggered zones unioned across detections | Task 3 |
| Two consecutive elevated frames → debounce met | Task 4 |
| Single elevated → not met | Task 4 |
| Too-far-apart → not met | Task 4 |
| Out-of-order sorted by frame_id | Task 4 |
| History bounded | Task 4 |
| YOLOAdapter filters dog class only | Task 7 |
| YOLOAdapter excludes below threshold | Task 7 |
| Device auto → best available / CPU fallback | Task 7 |
| Explicit device honored | Task 7 |
| Server: valid frame → detection returned | Task 8 |
| Server: processing error → error message + connection survives | Task 8 |
| Server: ping → pong | Task 8 |
| Camera opens + records dims | Task 9 |
| Camera open failure raises before loop | Task 9 |
| Transient read failure → continues | Task 9 (read returns None) |
| Frame-skip sends every Nth | Task 10 |
| Frame-skip=1 sends every frame | Task 10 |
| Frame sent + detection matched + latency measured | Task 10 |
| Server error handled (logged, continues) | Task 10 |
| Connection retry on initial failure | Task 10 (test_camera_released_on_stop) |
| Reconnect after mid-session disconnect | Task 10 (_run_connection re-raises → supervisor loops) |
| Graceful shutdown releases camera + socket | Task 10 (test_camera_released_on_stop) |
| Elevated dog reported with zones (E2E) | Task 11 |
| Floor dog reported not-elevated (E2E) | Task 11 |
| 100% coverage | Task 12 |
| Ruff lint + format | Task 12 |
| Docstrings on all public symbols | Task 12 |

### Known coverage gap to address during implementation

`counter_cruiser/server/model.py` imports `torch` and `YOLO` at module level inside a `try/except ImportError`. The `except` branch is `# pragma: no cover` (server extra not installed in dev; we test via mocks). Add the pragma before committing Task 7.
