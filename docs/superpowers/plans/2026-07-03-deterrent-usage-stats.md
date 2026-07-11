---
change: deterrent-usage-stats
design-doc: docs/superpowers/specs/2026-07-03-deterrent-usage-stats-design.md
base-ref: a46e684b5210781fd1fb52b2f3b831e794ef469c
archived-with: 2026-07-11-deterrent-usage-stats
---

# Deterrent Usage Stats Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Persistently record every attempted deterrent-trigger outcome in SQLite, expose the deterrent's operational status, and surface both as a `/training-progress` page (day/week bucketed usage trend + recent failures) and a brief dashboard summary — all gated by the existing `alerts.deterrent.enabled` flag, no new config toggle.

**Architecture:** A new `DeterrentStatsStore` (stdlib `sqlite3`, WAL mode, one fresh connection per access — mirroring `ZoneStore`'s no-shared-handle pattern) is constructed once at client startup and injected into `DeterrentHandler` (which records one event per `trigger()` call) and into the Flask app (which reads it for a new `/api/deterrent-stats` JSON endpoint). `DeterrentHandler` also gains a read-only `is_operational` property, pushed into `DashboardState` once at startup as a new `DeterrentStatus` value. `/training-progress` is a new template whose JS does all day/week bucketing and SVG bar rendering client-side from the raw event list returned by the one JSON endpoint; the dashboard page reuses that same endpoint for a one-line summary. No new third-party dependency.

**Tech Stack:** Python 3.12+, stdlib `sqlite3`, Flask (existing `web/` package), Pydantic v2 (`DeterrentConfig`), pytest + pytest-cov, hand-rolled vanilla JS (no build step, matching `dashboard.html`/`calibration.html`).

## Global Constraints

- 100% line + branch coverage required (`--cov-fail-under=100`), enforced project-wide — copied verbatim from `AGENTS.md`/`CLAUDE.md` and `design.md`'s Impact section.
- No module-level mutable state; dependency injection throughout (matches every existing `web/` module — `app.py`, `zone_store.py`, `state.py`).
- Logging facade only — no `print()` anywhere.
- Docstrings required on all public modules/classes/functions added or modified.
- `ruff check .` and `ruff format .` must be clean before finalization.
- No new config flag to enable/disable stats tracking — gated by the existing `alerts.deterrent.enabled` (proposal.md, "Explicitly not in scope").
- No pruning/retention limit on recorded events — unbounded retention is intentional (design.md Non-Goals).
- No new third-party dependency and no new frontend/JS dependency — stdlib `sqlite3` only, hand-rolled inline SVG (design.md Decisions).
- SQLite access: fresh `sqlite3.connect(path)` per read/write, `PRAGMA journal_mode=WAL` per connection, no shared long-lived connection, no `threading.Lock` (design.md Storage section) — python-resource-management: treat each access as its own resource lifetime, closed via `with self._connect() as conn:`.
- `since_days=182` and failure `limit=50` are named module-level constants, not magic numbers, matching `_DEFAULT_ALERT_HISTORY_CAPACITY` in `state.py` (design.md Data Endpoint section) — python-code-style: `SCREAMING_SNAKE_CASE` constants.

archived-with: 2026-07-11-deterrent-usage-stats
---

### Task 1: `DeterrentConfig.stats_db_path` field

**Files:**
- Modify: `counter_cruiser/config/models.py:55-77` (`DeterrentConfig`)
- Test: `tests/config/test_config.py:167-194` (`TestDeterrentConfig`)

**Interfaces:**
- Produces: `DeterrentConfig.stats_db_path: str` (default `'./deterrent_stats.db'`), consumed by Task 9's `__main__.py` wiring.

- [x] **Step 1: Write the failing test**

Add to `tests/config/test_config.py` inside `class TestDeterrentConfig:`:

```python
    def test_stats_db_path_default(self) -> None:
        c = DeterrentConfig()
        assert c.stats_db_path == './deterrent_stats.db'

    def test_stats_db_path_overridable(self) -> None:
        c = DeterrentConfig(stats_db_path='/data/stats.db')
        assert c.stats_db_path == '/data/stats.db'
```

- [x] **Step 2: Run test to verify it fails**

Run: `pytest tests/config/test_config.py::TestDeterrentConfig -v`
Expected: FAIL with `AttributeError: 'DeterrentConfig' object has no attribute 'stats_db_path'` (Pydantic v2's `extra='forbid'` model won't raise on read of a missing attribute the way plain classes do, but the assertion `c.stats_db_path` will raise `AttributeError` since the field doesn't exist yet).

- [x] **Step 3: Write minimal implementation**

In `counter_cruiser/config/models.py`, inside `class DeterrentConfig(BaseModel):` (after `burst_duration_seconds: float = 1.5`):

```python
    burst_duration_seconds: float = 1.5
    stats_db_path: str = './deterrent_stats.db'
```

- [x] **Step 4: Run test to verify it passes**

Run: `pytest tests/config/test_config.py::TestDeterrentConfig -v`
Expected: PASS (all `TestDeterrentConfig` tests, including the two new ones)

- [x] **Step 5: Commit**

```bash
git add counter_cruiser/config/models.py tests/config/test_config.py
git commit -m "feat(deterrent-usage-stats): add DeterrentConfig.stats_db_path"
```

archived-with: 2026-07-11-deterrent-usage-stats
---

### Task 2: `DeterrentStatsStore` — SQLite-backed event recorder

**Files:**
- Create: `counter_cruiser/client/deterrent_stats.py`
- Test: `tests/client/test_deterrent_stats.py`

**Interfaces:**
- Consumes: nothing from earlier tasks (standalone module; only needs a filesystem path).
- Produces: `DeterrentStatsStore(db_path: Path)` with `.record(succeeded: bool) -> None`, `.recent_events(since_days: int) -> list[tuple[str, bool]]`, `.recent_failures(limit: int) -> list[str]`. Consumed by Task 3 (`DeterrentHandler`) and Task 5 (`routes_deterrent_stats.py`).

This is the store from the design doc's "Storage" section, transcribed verbatim (design doc already gives full working code — this task adds the module, docstrings, and tests around it).

- [x] **Step 1: Write the failing tests**

Create `tests/client/test_deterrent_stats.py`:

```python
"""Tests for DeterrentStatsStore: SQLite-backed deterrent event recording."""

from __future__ import annotations

import sqlite3
import threading
from datetime import UTC, datetime, timedelta

from counter_cruiser.client.deterrent_stats import DeterrentStatsStore


class TestRecordAndRetrieve:
    def test_recent_events_empty_when_nothing_recorded(self, tmp_path) -> None:
        store = DeterrentStatsStore(tmp_path / 'stats.db')
        assert store.recent_events(since_days=30) == []

    def test_record_then_recent_events_round_trips(self, tmp_path) -> None:
        store = DeterrentStatsStore(tmp_path / 'stats.db')
        store.record(succeeded=True)
        store.record(succeeded=False)
        events = store.recent_events(since_days=30)
        assert len(events) == 2
        assert [succeeded for _, succeeded in events] == [True, False]
        # timestamps are ISO 8601 strings, ascending order
        assert events[0][0] <= events[1][0]

    def test_recent_events_excludes_events_older_than_cutoff(self, tmp_path) -> None:
        store = DeterrentStatsStore(tmp_path / 'stats.db')
        old_ts = (datetime.now(UTC) - timedelta(days=400)).isoformat()
        with sqlite3.connect(tmp_path / 'stats.db') as conn:
            conn.execute(
                'INSERT INTO deterrent_events (timestamp_utc, succeeded) '
                'VALUES (?, ?)',
                (old_ts, 1),
            )
        store.record(succeeded=True)
        events = store.recent_events(since_days=30)
        assert len(events) == 1

    def test_recent_failures_returns_only_failures_newest_first(self, tmp_path) -> None:
        store = DeterrentStatsStore(tmp_path / 'stats.db')
        store.record(succeeded=True)
        store.record(succeeded=False)
        store.record(succeeded=False)
        failures = store.recent_failures(limit=50)
        assert len(failures) == 2
        assert failures[0] >= failures[1]  # newest first

    def test_recent_failures_respects_limit(self, tmp_path) -> None:
        store = DeterrentStatsStore(tmp_path / 'stats.db')
        for _ in range(5):
            store.record(succeeded=False)
        assert len(store.recent_failures(limit=3)) == 3

    def test_recent_failures_empty_when_no_failures(self, tmp_path) -> None:
        store = DeterrentStatsStore(tmp_path / 'stats.db')
        store.record(succeeded=True)
        assert store.recent_failures(limit=50) == []


class TestPersistence:
    def test_events_survive_a_fresh_store_instance(self, tmp_path) -> None:
        """Simulates a client restart: a new DeterrentStatsStore pointed at
        the same file sees events recorded by a prior instance."""
        db_path = tmp_path / 'stats.db'
        first = DeterrentStatsStore(db_path)
        first.record(succeeded=True)

        second = DeterrentStatsStore(db_path)
        events = second.recent_events(since_days=30)
        assert len(events) == 1
        assert events[0][1] is True


class TestWalMode:
    def test_journal_mode_is_wal(self, tmp_path) -> None:
        db_path = tmp_path / 'stats.db'
        DeterrentStatsStore(db_path)
        with sqlite3.connect(db_path) as conn:
            mode = conn.execute('PRAGMA journal_mode').fetchone()[0]
        assert mode.lower() == 'wal'


class TestConcurrency:
    def test_concurrent_writes_and_reads_do_not_raise_or_corrupt(self, tmp_path) -> None:
        """Regression guard: a writer thread and a reader thread hitting the
        same store concurrently must not raise or leave torn/duplicated
        rows, mirroring web-ui's ZoneStore concurrency test shape."""
        store = DeterrentStatsStore(tmp_path / 'stats.db')
        errors: list[Exception] = []

        def writer() -> None:
            try:
                for i in range(20):
                    store.record(succeeded=i % 2 == 0)
            except Exception as exc:  # pragma: no cover - failure path only
                errors.append(exc)

        def reader() -> None:
            try:
                for _ in range(20):
                    store.recent_events(since_days=30)
                    store.recent_failures(limit=50)
            except Exception as exc:  # pragma: no cover - failure path only
                errors.append(exc)

        threads = [
            threading.Thread(target=writer),
            threading.Thread(target=reader),
            threading.Thread(target=reader),
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        assert errors == []
        events = store.recent_events(since_days=30)
        assert len(events) == 20
```

- [x] **Step 2: Run tests to verify they fail**

Run: `pytest tests/client/test_deterrent_stats.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'counter_cruiser.client.deterrent_stats'`

- [x] **Step 3: Write minimal implementation**

Create `counter_cruiser/client/deterrent_stats.py`:

```python
"""SQLite-backed persistent recorder for deterrent trigger attempts.

One row per attempted trigger (timestamp + succeeded flag), surviving
client restarts. Mirrors ZoneStore's access pattern from the web-ui
change: a fresh connection per read/write, WAL mode, no shared long-lived
connection and no threading.Lock — SQLite's single-writer/multiple-reader
WAL semantics already make this safe across the asyncio detection thread
(writer) and the Flask request threads (readers).
"""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path


class DeterrentStatsStore:
    """SQLite-backed recorder for deterrent trigger attempts."""

    def __init__(self, db_path: Path) -> None:
        """Store the target database path and ensure the schema exists."""
        self._db_path = db_path
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        """Open a fresh connection with WAL mode enabled."""
        conn = sqlite3.connect(self._db_path)
        conn.execute('PRAGMA journal_mode=WAL')
        return conn

    def _init_schema(self) -> None:
        """Create the deterrent_events table if it does not already exist."""
        with self._connect() as conn:
            conn.execute(
                'CREATE TABLE IF NOT EXISTS deterrent_events ('
                'id INTEGER PRIMARY KEY AUTOINCREMENT, '
                'timestamp_utc TEXT NOT NULL, '
                'succeeded INTEGER NOT NULL)'
            )

    def record(self, succeeded: bool) -> None:
        """Insert one event row for the current UTC time."""
        with self._connect() as conn:
            conn.execute(
                'INSERT INTO deterrent_events (timestamp_utc, succeeded) '
                'VALUES (?, ?)',
                (datetime.now(UTC).isoformat(), int(succeeded)),
            )

    def recent_events(self, since_days: int) -> list[tuple[str, bool]]:
        """Return (timestamp_utc, succeeded) for events within the last *since_days*."""
        cutoff = (datetime.now(UTC) - timedelta(days=since_days)).isoformat()
        with self._connect() as conn:
            rows = conn.execute(
                'SELECT timestamp_utc, succeeded FROM deterrent_events '
                'WHERE timestamp_utc >= ? ORDER BY timestamp_utc ASC',
                (cutoff,),
            ).fetchall()
        return [(ts, bool(s)) for ts, s in rows]

    def recent_failures(self, limit: int) -> list[str]:
        """Return up to *limit* most recent failed-event timestamps, newest first."""
        with self._connect() as conn:
            rows = conn.execute(
                'SELECT timestamp_utc FROM deterrent_events '
                'WHERE succeeded = 0 ORDER BY timestamp_utc DESC LIMIT ?',
                (limit,),
            ).fetchall()
        return [ts for (ts,) in rows]
```

- [x] **Step 4: Run tests to verify they pass**

Run: `pytest tests/client/test_deterrent_stats.py -v`
Expected: PASS (all tests)

- [x] **Step 5: Run with coverage to confirm 100% on the new module**

Run: `pytest tests/client/test_deterrent_stats.py --cov=counter_cruiser.client.deterrent_stats --cov-report=term-missing`
Expected: `counter_cruiser/client/deterrent_stats.py` at 100%

- [x] **Step 6: Commit**

```bash
git add counter_cruiser/client/deterrent_stats.py tests/client/test_deterrent_stats.py
git commit -m "feat(deterrent-usage-stats): add DeterrentStatsStore SQLite recorder"
```

archived-with: 2026-07-11-deterrent-usage-stats
---

### Task 3: `DeterrentHandler` — `is_operational` property + trigger recording

**Files:**
- Modify: `counter_cruiser/client/alerts/deterrent.py`
- Test: `tests/client/alerts/test_deterrent.py` (extend; also update every existing `DeterrentHandler(config)` call site to pass a stats store, since the constructor signature changes)

**Interfaces:**
- Consumes: `DeterrentStatsStore` from Task 2 (`.record(succeeded: bool) -> None`).
- Produces: `DeterrentHandler(config: DeterrentConfig, stats_store: DeterrentStatsStore)`, `DeterrentHandler.is_operational -> bool` property. Consumed by Task 9's `_build_alert_manager`.

`DeterrentHandler`'s constructor becomes a required two-argument call. Every existing call in `tests/client/alerts/test_deterrent.py` (`DeterrentHandler(config)`) must be updated to `DeterrentHandler(config, _fake_stats_store())`.

- [x] **Step 1: Write the failing tests**

Add a fake store helper and new tests to `tests/client/alerts/test_deterrent.py`. First, add near the top (after `_fake_gpio`):

```python
class _FakeStatsStore:
    """Records .record() calls in-memory; stands in for DeterrentStatsStore."""

    def __init__(self) -> None:
        self.recorded: list[bool] = []

    def record(self, succeeded: bool) -> None:
        self.recorded.append(succeeded)
```

Then update every existing `DeterrentHandler(config)` construction in the file to `DeterrentHandler(config, _FakeStatsStore())` (there are 8 call sites: `test_burst_drives_pin_high_then_low`, `test_burst_uses_configured_duration`, `test_pin_driven_low_after_a_normal_burst`, `test_pin_driven_low_and_error_logged_when_burst_raises`, `test_missing_gpio_library_disables_handler_with_log`, `test_gpio_setup_failure_disables_handler_with_log`, `test_disabled_by_config_trigger_is_a_noop`, `test_cleanup_releases_gpio_after_init`, `test_cleanup_is_safe_when_disabled`, `test_cleanup_does_not_raise_when_gpio_cleanup_raises`, `test_trigger_does_not_raise_when_final_gpio_output_raises`).

Add these new test classes at the end of the file:

```python
class TestIsOperational:
    def test_operational_after_successful_gpio_setup(self) -> None:
        gpio = _fake_gpio()
        config = DeterrentConfig(enabled=True, pin=17)
        with patch(
            'counter_cruiser.client.alerts.deterrent._import_gpio',
            return_value=gpio,
        ):
            handler = DeterrentHandler(config, _FakeStatsStore())
        assert handler.is_operational is True

    def test_not_operational_when_gpio_unavailable(self) -> None:
        config = DeterrentConfig(enabled=True, pin=17)
        with patch(
            'counter_cruiser.client.alerts.deterrent._import_gpio',
            return_value=None,
        ):
            handler = DeterrentHandler(config, _FakeStatsStore())
        assert handler.is_operational is False

    def test_not_operational_when_setup_fails(self) -> None:
        gpio = _fake_gpio()
        gpio.setup.side_effect = RuntimeError('no such pin')
        config = DeterrentConfig(enabled=True, pin=17)
        with patch(
            'counter_cruiser.client.alerts.deterrent._import_gpio',
            return_value=gpio,
        ):
            handler = DeterrentHandler(config, _FakeStatsStore())
        assert handler.is_operational is False

    def test_not_operational_when_disabled_by_config(self) -> None:
        config = DeterrentConfig(enabled=False)
        handler = DeterrentHandler(config, _FakeStatsStore())
        assert handler.is_operational is False


class TestTriggerRecordsOutcome:
    def test_successful_trigger_records_succeeded_true(self) -> None:
        gpio = _fake_gpio()
        config = DeterrentConfig(enabled=True, pin=17, burst_duration_seconds=0.01)
        stats_store = _FakeStatsStore()
        with (
            patch(
                'counter_cruiser.client.alerts.deterrent._import_gpio',
                return_value=gpio,
            ),
            patch('counter_cruiser.client.alerts.deterrent.time.sleep'),
        ):
            handler = DeterrentHandler(config, stats_store)
            handler.trigger(_context())
        assert stats_store.recorded == [True]

    def test_erroring_burst_records_succeeded_false_and_still_drives_pin_low(
        self,
    ) -> None:
        gpio = _fake_gpio()
        config = DeterrentConfig(enabled=True, pin=17, burst_duration_seconds=0.01)
        stats_store = _FakeStatsStore()
        with (
            patch(
                'counter_cruiser.client.alerts.deterrent._import_gpio',
                return_value=gpio,
            ),
            patch(
                'counter_cruiser.client.alerts.deterrent.time.sleep',
                side_effect=RuntimeError('boom'),
            ),
        ):
            handler = DeterrentHandler(config, stats_store)
            handler.trigger(_context())
        assert stats_store.recorded == [False]
        assert gpio.output.call_args_list[-1] == ((17, gpio.LOW),)

    def test_disabled_handler_trigger_records_nothing(self) -> None:
        config = DeterrentConfig(enabled=False)
        stats_store = _FakeStatsStore()
        handler = DeterrentHandler(config, stats_store)
        handler.trigger(_context())
        assert stats_store.recorded == []

    def test_missing_gpio_trigger_records_nothing(self) -> None:
        config = DeterrentConfig(enabled=True, pin=17)
        stats_store = _FakeStatsStore()
        with patch(
            'counter_cruiser.client.alerts.deterrent._import_gpio',
            return_value=None,
        ):
            handler = DeterrentHandler(config, stats_store)
        handler.trigger(_context())
        assert stats_store.recorded == []
```

- [x] **Step 2: Run tests to verify they fail**

Run: `pytest tests/client/alerts/test_deterrent.py -v`
Expected: FAIL — `TypeError: DeterrentHandler.__init__() missing 1 required positional argument: 'stats_store'` on every updated call site, and `AttributeError: 'DeterrentHandler' object has no attribute 'is_operational'` on the new tests.

- [x] **Step 3: Write minimal implementation**

Replace `counter_cruiser/client/alerts/deterrent.py` in full:

```python
"""GPIO deterrent handler: simulates a button press on the ultrasonic trainer.

The Pi does not generate the ultrasonic tone itself; it drives a BCM pin
HIGH for a configured duration (simulating the trainer's momentary-press
button) then LOW, wrapped in try/finally so the pin never stays HIGH. Each
attempted trigger's outcome is recorded via the injected
DeterrentStatsStore for the deterrent-usage-stats capability.
"""

from __future__ import annotations

import logging
import time
from types import ModuleType

from counter_cruiser.client.alerts.context import AlertContext
from counter_cruiser.client.deterrent_stats import DeterrentStatsStore
from counter_cruiser.config.models import DeterrentConfig

logger = logging.getLogger(__name__)


def _import_gpio() -> ModuleType | None:
    """Import RPi.GPIO; return None if the library is unavailable.

    Isolated as a module-level function (not imported at module scope) so
    tests can patch this exact seam without needing the real library
    installed.
    """
    try:
        import RPi.GPIO as GPIO  # noqa: N814  # pragma: no cover
    except ImportError:
        return None
    return GPIO  # pragma: no cover


class DeterrentHandler:
    """Drives a BCM GPIO pin HIGH then LOW to simulate a trainer button press."""

    def __init__(self, config: DeterrentConfig, stats_store: DeterrentStatsStore) -> None:
        """Set up GPIO if enabled; self-disable on any failure."""
        self._config = config
        self._stats_store = stats_store
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

    @property
    def is_operational(self) -> bool:
        """Return whether GPIO setup succeeded and the handler is enabled."""
        return self._enabled

    def trigger(self, context: AlertContext) -> None:
        """Fire one timed burst: pin HIGH for burst_duration_seconds, then LOW.

        Records the attempt's outcome (succeeded/failed) via the injected
        stats store. A disabled handler returns before recording anything —
        no event is written when the deterrent isn't operational, since no
        real GPIO attempt was made.
        """
        if not self._enabled or self._gpio is None:
            return
        gpio = self._gpio
        pin = self._config.pin
        succeeded = True
        try:
            gpio.output(pin, gpio.HIGH)
            time.sleep(self._config.burst_duration_seconds)
        except Exception:
            succeeded = False
            logger.exception('Deterrent burst failed on pin %s', pin)
        finally:
            try:
                gpio.output(pin, gpio.LOW)
            except Exception:
                logger.exception('Error resetting pin %s to LOW', pin)
            self._stats_store.record(succeeded)

    def cleanup(self) -> None:
        """Release the GPIO resource; safe to call even if never set up."""
        if self._gpio is not None:
            try:
                self._gpio.cleanup()
            except Exception:
                logger.exception('Error during GPIO cleanup')
            finally:
                self._gpio = None
                self._enabled = False
```

- [x] **Step 4: Run tests to verify they pass**

Run: `pytest tests/client/alerts/test_deterrent.py -v`
Expected: PASS (all tests)

- [x] **Step 5: Confirm 100% coverage on the modified module**

Run: `pytest tests/client/alerts/test_deterrent.py --cov=counter_cruiser.client.alerts.deterrent --cov-report=term-missing`
Expected: 100%

- [x] **Step 6: Commit**

```bash
git add counter_cruiser/client/alerts/deterrent.py tests/client/alerts/test_deterrent.py
git commit -m "feat(deterrent-usage-stats): add is_operational and trigger-outcome recording to DeterrentHandler"
```

archived-with: 2026-07-11-deterrent-usage-stats
---

### Task 4: `DashboardState` — `DeterrentStatus` + set/get

**Files:**
- Modify: `counter_cruiser/client/web/state.py`
- Test: `tests/client/web/test_state.py`

**Interfaces:**
- Consumes: nothing new.
- Produces: `DeterrentStatus(configured: bool = False, operational: bool = False)` frozen dataclass; `DashboardState.set_deterrent_status(configured: bool, operational: bool) -> None`; `DashboardState.get_deterrent_status() -> DeterrentStatus`. Consumed by Task 5 (routes) and Task 9 (`__main__.py`).

- [x] **Step 1: Write the failing tests**

Add to `tests/client/web/test_state.py`:

```python
from counter_cruiser.client.web.state import DeterrentStatus


class TestDeterrentStatus:
    def test_default_status_is_not_configured_not_operational(self) -> None:
        state = DashboardState()
        status = state.get_deterrent_status()
        assert status.configured is False
        assert status.operational is False

    def test_set_and_get_round_trips(self) -> None:
        state = DashboardState()
        state.set_deterrent_status(configured=True, operational=True)
        status = state.get_deterrent_status()
        assert status.configured is True
        assert status.operational is True

    def test_configured_but_not_operational(self) -> None:
        state = DashboardState()
        state.set_deterrent_status(configured=True, operational=False)
        status = state.get_deterrent_status()
        assert status.configured is True
        assert status.operational is False
```

- [x] **Step 2: Run tests to verify they fail**

Run: `pytest tests/client/web/test_state.py::TestDeterrentStatus -v`
Expected: FAIL with `ImportError: cannot import name 'DeterrentStatus'`

- [x] **Step 3: Write minimal implementation**

In `counter_cruiser/client/web/state.py`, add after `StatsSnapshot` (before `AlertHistoryEntry`):

```python
@dataclass(frozen=True)
class DeterrentStatus:
    """Point-in-time deterrent configuration/health for the web UI."""

    configured: bool = False
    operational: bool = False
```

In `DashboardState.__init__`, after `self._alerts = deque(...)`:

```python
        self._deterrent_status = DeterrentStatus()
```

Add new methods (placed after `get_alerts`):

```python
    def set_deterrent_status(self, configured: bool, operational: bool) -> None:
        """Set the deterrent's configured/operational status.

        Called once at startup by main() — the deterrent's operational
        status is determined entirely by one-time GPIO setup and does not
        change at runtime (see DeterrentHandler.is_operational).
        """
        with self._lock:
            self._deterrent_status = DeterrentStatus(
                configured=configured, operational=operational
            )

    def get_deterrent_status(self) -> DeterrentStatus:
        """Return the current deterrent status."""
        with self._lock:
            return self._deterrent_status
```

- [x] **Step 4: Run tests to verify they pass**

Run: `pytest tests/client/web/test_state.py -v`
Expected: PASS (all tests, including pre-existing ones)

- [x] **Step 5: Confirm 100% coverage**

Run: `pytest tests/client/web/test_state.py --cov=counter_cruiser.client.web.state --cov-report=term-missing`
Expected: 100%

- [x] **Step 6: Commit**

```bash
git add counter_cruiser/client/web/state.py tests/client/web/test_state.py
git commit -m "feat(deterrent-usage-stats): add DeterrentStatus to DashboardState"
```

archived-with: 2026-07-11-deterrent-usage-stats
---

### Task 5: `/api/deterrent-stats` route + `create_app` wiring

**Files:**
- Create: `counter_cruiser/client/web/routes_deterrent_stats.py`
- Modify: `counter_cruiser/client/web/app.py` (add `stats_store` param, register new routes)
- Test: `tests/client/web/test_routes_deterrent_stats.py`
- Modify (call-site update only, new required `stats_store` arg): `tests/client/web/test_app.py`, `tests/client/web/test_routes_dashboard.py`, `tests/client/web/test_routes_live_feed.py`, `tests/client/web/test_routes_zones.py`

**Interfaces:**
- Consumes: `DeterrentStatsStore` from Task 2 (`.recent_events`, `.recent_failures`); `DashboardState.get_deterrent_status()` from Task 4.
- Produces: `register_deterrent_stats_routes(app: Flask, state: DashboardState, stats_store: DeterrentStatsStoreProtocol) -> None`; `create_app(state, settings, zone_store, stats_store)` (new 4th required positional/keyword param). Consumed by Task 6 (adds `/training-progress` to the same module) and Task 9 (`__main__.py`).

This task only wires the JSON endpoint. `/training-progress`'s HTML page is added to this same module in Task 6, but the `create_app`/`stats_store` plumbing must land now since every route module needing `stats_store` shares the one injection point.

- [x] **Step 1: Write the failing tests**

Create `tests/client/web/test_routes_deterrent_stats.py`:

```python
"""Tests for the /api/deterrent-stats JSON endpoint."""

from __future__ import annotations

from counter_cruiser.client.web.app import create_app
from counter_cruiser.client.web.state import DashboardState
from counter_cruiser.config.models import ClientSettings


class FakeZoneStore:
    def list_zones(self):
        return [], 0


class FakeStatsStore:
    def __init__(self, events=None, failures=None):
        self._events = events or []
        self._failures = failures or []

    def recent_events(self, since_days: int):
        return self._events

    def recent_failures(self, limit: int):
        return self._failures[:limit]


def _client(state=None, stats_store=None):
    state = state or DashboardState()
    stats_store = stats_store or FakeStatsStore()
    app = create_app(state, ClientSettings(), FakeZoneStore(), stats_store)
    return app.test_client(), state, stats_store


class TestDeterrentStatsEndpoint:
    def test_returns_json_with_expected_keys(self) -> None:
        client, _, _ = _client()
        response = client.get('/api/deterrent-stats')
        assert response.status_code == 200
        body = response.get_json()
        assert set(body) == {'configured', 'operational', 'events', 'recent_failures'}

    def test_reflects_not_configured_status(self) -> None:
        client, state, _ = _client()
        state.set_deterrent_status(configured=False, operational=False)
        body = client.get('/api/deterrent-stats').get_json()
        assert body['configured'] is False
        assert body['operational'] is False

    def test_reflects_configured_and_operational_status(self) -> None:
        client, state, _ = _client()
        state.set_deterrent_status(configured=True, operational=True)
        body = client.get('/api/deterrent-stats').get_json()
        assert body['configured'] is True
        assert body['operational'] is True

    def test_events_are_serialized_from_the_store(self) -> None:
        stats_store = FakeStatsStore(
            events=[('2026-01-01T00:00:00+00:00', True), ('2026-01-02T00:00:00+00:00', False)]
        )
        client, _, _ = _client(stats_store=stats_store)
        body = client.get('/api/deterrent-stats').get_json()
        assert body['events'] == [
            {'timestamp_utc': '2026-01-01T00:00:00+00:00', 'succeeded': True},
            {'timestamp_utc': '2026-01-02T00:00:00+00:00', 'succeeded': False},
        ]

    def test_no_events_returns_empty_list(self) -> None:
        client, _, _ = _client()
        body = client.get('/api/deterrent-stats').get_json()
        assert body['events'] == []

    def test_recent_failures_are_included(self) -> None:
        stats_store = FakeStatsStore(failures=['2026-01-02T00:00:00+00:00'])
        client, _, _ = _client(stats_store=stats_store)
        body = client.get('/api/deterrent-stats').get_json()
        assert body['recent_failures'] == ['2026-01-02T00:00:00+00:00']
```

- [x] **Step 2: Run tests to verify they fail**

Run: `pytest tests/client/web/test_routes_deterrent_stats.py -v`
Expected: FAIL with `TypeError: create_app() takes 3 positional arguments but 4 were given`

- [x] **Step 3: Write minimal implementation**

Create `counter_cruiser/client/web/routes_deterrent_stats.py`:

```python
"""Deterrent usage-stats JSON endpoint: recent events + operational status."""

from __future__ import annotations

from typing import Protocol

from flask import Flask, jsonify

from counter_cruiser.client.web.state import DashboardState

_SINCE_DAYS = 182
_FAILURE_LIMIT = 50


class DeterrentStatsStoreProtocol(Protocol):
    """Structural interface the route depends on for stats retrieval."""

    def recent_events(self, since_days: int) -> list[tuple[str, bool]]:
        """Return (timestamp_utc, succeeded) pairs within since_days."""
        ...  # pragma: no cover

    def recent_failures(self, limit: int) -> list[str]:
        """Return up to limit most recent failed-event timestamps."""
        ...  # pragma: no cover


def register_deterrent_stats_routes(
    app: Flask, state: DashboardState, stats_store: DeterrentStatsStoreProtocol
) -> None:
    """Register the deterrent usage-stats JSON endpoint on *app*."""

    @app.get('/api/deterrent-stats')
    def deterrent_stats():
        status = state.get_deterrent_status()
        events = stats_store.recent_events(since_days=_SINCE_DAYS)
        failures = stats_store.recent_failures(limit=_FAILURE_LIMIT)
        return jsonify(
            {
                'configured': status.configured,
                'operational': status.operational,
                'events': [
                    {'timestamp_utc': ts, 'succeeded': ok} for ts, ok in events
                ],
                'recent_failures': failures,
            }
        )
```

Modify `counter_cruiser/client/web/app.py`:

```python
from counter_cruiser.client.web.routes_dashboard import register_dashboard_routes
from counter_cruiser.client.web.routes_deterrent_stats import (
    DeterrentStatsStoreProtocol,
    register_deterrent_stats_routes,
)
from counter_cruiser.client.web.routes_live_feed import register_live_feed_routes
from counter_cruiser.client.web.routes_zones import register_zone_routes
from counter_cruiser.client.web.state import DashboardState
from counter_cruiser.config.models import ClientSettings, Zone
```

Update `create_app` and `_register_all_routes`:

```python
def create_app(
    state: DashboardState,
    settings: ClientSettings,
    zone_store: ZoneStoreProtocol,
    stats_store: DeterrentStatsStoreProtocol,
) -> Flask:
    """Build and return a Flask app wired to the injected collaborators."""
    app = Flask(__name__, template_folder=str(_TEMPLATES_DIR))
    _register_all_routes(app, state, settings, zone_store, stats_store)
    return app


def _register_all_routes(
    app: Flask,
    state: DashboardState,
    settings: ClientSettings,
    zone_store: ZoneStoreProtocol,
    stats_store: DeterrentStatsStoreProtocol,
) -> None:
    """Register every route module's handlers on *app*.

    Split out so later tasks can add a `register_*_routes` call each without
    growing `create_app` itself — each import is added by the task that
    introduces the corresponding route module.
    """
    register_dashboard_routes(app, state)
    register_live_feed_routes(app, state, settings, zone_store)
    register_zone_routes(app, zone_store)
    register_deterrent_stats_routes(app, state, stats_store)
```

Update the four existing test files' `create_app(...)` calls to pass a fourth argument. In each of `tests/client/web/test_app.py`, `tests/client/web/test_routes_dashboard.py`, `tests/client/web/test_routes_live_feed.py`, `tests/client/web/test_routes_zones.py`, add a minimal fake near the top:

```python
class FakeStatsStore:
    def recent_events(self, since_days: int):
        return []

    def recent_failures(self, limit: int):
        return []
```

...and append `, FakeStatsStore()` to every `create_app(...)` call found by:
`grep -n "create_app(" tests/client/web/test_app.py tests/client/web/test_routes_dashboard.py tests/client/web/test_routes_live_feed.py tests/client/web/test_routes_zones.py`

- [x] **Step 4: Run tests to verify they pass**

Run: `pytest tests/client/web/ -v`
Expected: PASS (all tests in `tests/client/web/`, including the four updated files and the new `test_routes_deterrent_stats.py`)

- [x] **Step 5: Confirm 100% coverage**

Run: `pytest tests/client/web/ --cov=counter_cruiser.client.web --cov-report=term-missing`
Expected: 100% on `app.py` and `routes_deterrent_stats.py` (other modules' coverage unaffected by this task)

- [x] **Step 6: Commit**

```bash
git add counter_cruiser/client/web/routes_deterrent_stats.py counter_cruiser/client/web/app.py \
  tests/client/web/test_routes_deterrent_stats.py tests/client/web/test_app.py \
  tests/client/web/test_routes_dashboard.py tests/client/web/test_routes_live_feed.py \
  tests/client/web/test_routes_zones.py
git commit -m "feat(deterrent-usage-stats): add /api/deterrent-stats endpoint"
```

archived-with: 2026-07-11-deterrent-usage-stats
---

### Task 6: `/training-progress` route + page skeleton (Python-testable parts)

**Files:**
- Modify: `counter_cruiser/client/web/routes_deterrent_stats.py` (add the page route)
- Create: `counter_cruiser/client/web/templates/training_progress.html` (skeleton only — static HTML shell + `<script>` tag; JS body filled in by Task 7)
- Test: `tests/client/web/test_routes_deterrent_stats.py` (extend)

**Interfaces:**
- Consumes: nothing new (page is server-side-static; all data comes from `/api/deterrent-stats` client-side, per design.md).
- Produces: `GET /training-progress` route serving `training_progress.html`. Consumed by Task 7 (fills in the `<script>` body) and Task 8 (dashboard links to this route by name).

Per the design doc's "no server-side templating of the actual event data" — this task only needs to prove the route/template plumbing works, including the documented no-events-yet scenario (which is a page-serves-successfully assertion, not a specific rendered value, since rendering is client-side).

- [x] **Step 1: Write the failing tests**

Add to `tests/client/web/test_routes_deterrent_stats.py`:

```python
class TestTrainingProgressPage:
    def test_page_is_served(self) -> None:
        client, _, _ = _client()
        response = client.get('/training-progress')
        assert response.status_code == 200
        assert b'<html' in response.data

    def test_page_renders_with_no_events_yet(self) -> None:
        """The page must serve successfully even with zero recorded events —
        the no-events-yet state is handled by the page's own JS, not the
        server, but the route itself must never error on an empty store."""
        stats_store = FakeStatsStore(events=[], failures=[])
        client, _, _ = _client(stats_store=stats_store)
        response = client.get('/training-progress')
        assert response.status_code == 200
```

- [x] **Step 2: Run tests to verify they fail**

Run: `pytest tests/client/web/test_routes_deterrent_stats.py::TestTrainingProgressPage -v`
Expected: FAIL with 404 (`assert 404 == 200`) — no `/training-progress` route registered yet.

- [x] **Step 3: Write minimal implementation**

In `counter_cruiser/client/web/routes_deterrent_stats.py`, add `render_template` to the Flask import and add the new route inside `register_deterrent_stats_routes`:

```python
from flask import Flask, jsonify, render_template
```

```python
    @app.get('/training-progress')
    def training_progress():
        return render_template('training_progress.html')
```

Create `counter_cruiser/client/web/templates/training_progress.html` (skeleton; Task 7 fills in the `<script>` body marked below):

```html
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Counter Cruiser — Training Progress</title>
</head>
<body>
  <h1>Training Progress</h1>
  <p><a href="{{ url_for('dashboard') }}">Back to dashboard</a></p>
  <section id="operational-status">
    <p>Deterrent: <span id="deterrent-status">loading…</span></p>
  </section>
  <section id="chart-controls">
    <button id="view-day" type="button">Day view</button>
    <button id="view-week" type="button">Week view</button>
  </section>
  <section id="chart-section">
    <svg id="usage-chart" width="800" height="200"></svg>
    <p id="no-events-message" hidden>No corrections recorded yet.</p>
  </section>
  <section id="failures-section">
    <h2>Recent failures</h2>
    <label>Show last
      <input id="failure-count" type="number" min="1" value="5">
      failures
    </label>
    <div id="failure-list" style="max-height: 200px; overflow-y: auto;"></div>
  </section>
  <script>
    // Filled in by Task 7: fetch('/api/deterrent-stats'), local-time
    // conversion, day/week bucketing, SVG bar rendering, failure list.
  </script>
</body>
</html>
```

- [x] **Step 4: Run tests to verify they pass**

Run: `pytest tests/client/web/test_routes_deterrent_stats.py -v`
Expected: PASS (all tests, including the two new ones)

- [x] **Step 5: Confirm 100% coverage**

Run: `pytest tests/client/web/test_routes_deterrent_stats.py --cov=counter_cruiser.client.web.routes_deterrent_stats --cov-report=term-missing`
Expected: 100%

- [x] **Step 6: Commit**

```bash
git add counter_cruiser/client/web/routes_deterrent_stats.py \
  counter_cruiser/client/web/templates/training_progress.html \
  tests/client/web/test_routes_deterrent_stats.py
git commit -m "feat(deterrent-usage-stats): add /training-progress route and page skeleton"
```

archived-with: 2026-07-11-deterrent-usage-stats
---

### Task 7: `/training-progress` client-side JS — bucketing, SVG chart, failures panel

**Files:**
- Modify: `counter_cruiser/client/web/templates/training_progress.html` (fill in the `<script>` body only)

**Interfaces:**
- Consumes: `GET /api/deterrent-stats` (Task 5's JSON shape: `{configured, operational, events: [{timestamp_utc, succeeded}], recent_failures: [timestamp_utc, ...]}`).
- Produces: none consumed by later tasks — this is the leaf of the dependency chain for the training-progress page.

**Why this task has no automated test:** there is no JS test runner in this project (confirmed by `package.json` absence and every existing template — `dashboard.html`, `calibration.html` — using plain inline `<script>` with zero test coverage). This is a pre-existing gap in the project's otherwise-100%-Python-coverage discipline, not one this change should silently paper over. Verification here is **structural code review against a literal worked example**, specified in Step 2 below, plus a manual browser check in Step 3.

- [x] **Step 1: Implement the JS**

Replace the `<script>` block in `counter_cruiser/client/web/templates/training_progress.html` with:

```html
  <script>
    let allEvents = [];
    let currentView = 'day';

    function toLocalDate(timestampUtc) {
      return new Date(timestampUtc);
    }

    // Monday-start ISO week key, e.g. "2026-W01", from a local Date.
    function isoWeekKey(date) {
      const d = new Date(date.getFullYear(), date.getMonth(), date.getDate());
      const dayNum = (d.getDay() + 6) % 7; // Monday=0 ... Sunday=6
      d.setDate(d.getDate() - dayNum + 3); // nearest Thursday
      const firstThursday = new Date(d.getFullYear(), 0, 4);
      const firstThursdayDayNum = (firstThursday.getDay() + 6) % 7;
      firstThursday.setDate(firstThursday.getDate() - firstThursdayDayNum + 3);
      const weekNum = 1 + Math.round((d - firstThursday) / (7 * 86400000));
      return `${d.getFullYear()}-W${String(weekNum).padStart(2, '0')}`;
    }

    function dayKey(date) {
      const y = date.getFullYear();
      const m = String(date.getMonth() + 1).padStart(2, '0');
      const day = String(date.getDate()).padStart(2, '0');
      return `${y}-${m}-${day}`;
    }

    function bucketEvents(events, granularity, windowCount) {
      const now = new Date();
      const keys = [];
      if (granularity === 'day') {
        for (let i = windowCount - 1; i >= 0; i--) {
          const d = new Date(now);
          d.setDate(d.getDate() - i);
          keys.push(dayKey(d));
        }
      } else {
        for (let i = windowCount - 1; i >= 0; i--) {
          const d = new Date(now);
          d.setDate(d.getDate() - i * 7);
          keys.push(isoWeekKey(d));
        }
      }
      const counts = Object.fromEntries(keys.map((k) => [k, 0]));
      for (const event of events) {
        const local = toLocalDate(event.timestamp_utc);
        const key = granularity === 'day' ? dayKey(local) : isoWeekKey(local);
        if (key in counts) {
          counts[key] += 1;
        }
      }
      return keys.map((k) => ({ key: k, count: counts[k] }));
    }

    function renderChart(buckets) {
      const svg = document.getElementById('usage-chart');
      const noEventsMessage = document.getElementById('no-events-message');
      svg.innerHTML = '';
      const total = buckets.reduce((sum, b) => sum + b.count, 0);
      noEventsMessage.hidden = total > 0;
      if (total === 0) {
        return;
      }
      const width = 800;
      const height = 200;
      const barGap = 2;
      const barWidth = width / buckets.length - barGap;
      const maxCount = Math.max(...buckets.map((b) => b.count), 1);
      buckets.forEach((bucket, i) => {
        const barHeight = (bucket.count / maxCount) * (height - 20);
        const rect = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
        rect.setAttribute('x', i * (barWidth + barGap));
        rect.setAttribute('y', height - barHeight);
        rect.setAttribute('width', barWidth);
        rect.setAttribute('height', barHeight);
        rect.setAttribute('fill', 'steelblue');
        const title = document.createElementNS('http://www.w3.org/2000/svg', 'title');
        title.textContent = `${bucket.key}: ${bucket.count}`;
        rect.appendChild(title);
        svg.appendChild(rect);
      });
    }

    function renderStatus(configured, operational) {
      const el = document.getElementById('deterrent-status');
      if (!configured) {
        el.textContent = 'not configured';
      } else if (operational) {
        el.textContent = 'configured — healthy';
      } else {
        el.textContent = 'configured — not operational';
      }
    }

    function renderFailures(failures) {
      const count = parseInt(document.getElementById('failure-count').value, 10) || 5;
      const list = document.getElementById('failure-list');
      list.innerHTML = '';
      for (const ts of failures.slice(0, count)) {
        const p = document.createElement('p');
        p.textContent = toLocalDate(ts).toLocaleString();
        list.appendChild(p);
      }
    }

    function renderCurrentView(data) {
      const windowCount = currentView === 'day' ? 30 : 26;
      const buckets = bucketEvents(allEvents, currentView, windowCount);
      renderChart(buckets);
    }

    async function load() {
      const data = await (await fetch('/api/deterrent-stats')).json();
      allEvents = data.events;
      renderStatus(data.configured, data.operational);
      renderCurrentView(data);
      renderFailures(data.recent_failures);
    }

    document.getElementById('view-day').addEventListener('click', () => {
      currentView = 'day';
      renderCurrentView();
    });
    document.getElementById('view-week').addEventListener('click', () => {
      currentView = 'week';
      renderCurrentView();
    });
    document.getElementById('failure-count').addEventListener('input', load);

    load();
  </script>
```

- [x] **Step 2: Structural verification against a literal worked example**

By inspection (no test runner available for JS in this project — see rationale above), trace `bucketEvents` against this literal dataset and confirm the stated results by hand-evaluating the function body:

Given `now` = a Wednesday, and `events` (as local-time-equivalent ISO strings after `toLocalDate`):
- 3 events on `now` (today)
- 2 events on `now - 1 day` (yesterday)
- 1 event on `now - 40 days` (outside the 30-day day-view window)

Expected for `bucketEvents(events, 'day', 30)`:
- The returned array has exactly 30 entries, keys ascending from `now - 29 days` to `now`.
- The last entry (`key === dayKey(now)`) has `count === 3`.
- The second-to-last entry has `count === 2`.
- No entry has a nonzero count from the 40-days-ago event (it falls outside all 30 generated keys, and since `counts` is only pre-seeded for keys within the window, that event's `dayKey` is never added as a spurious key — confirm by reading the `if (key in counts)` guard in the loop, which silently drops any event whose bucket key isn't in the pre-seeded window).
- Every other entry has `count === 0`.

Expected for `bucketEvents(events, 'week', 26)`: the same 6 events described above collapse into at most 2 week buckets (this week and, if `now - 40 days` crosses a week boundary from the other 5 events, up to one more); confirm `isoWeekKey` groups `now` and `now - 1 day` into the same key when they fall in the same Mon-Sun week (true unless `now` is a Monday), and confirm the `now - 40 days` event's key is outside the 26-key window and is silently dropped, matching the day-view behavior.

Record the outcome of this trace in the task's commit message or PR description (e.g. "traced bucketEvents against the 3-events-today/2-yesterday/1-forty-days-ago example; day view: last bucket=3, second-to-last=2, rest=0, out-of-window event dropped; week view: collapses to 1-2 buckets as expected").

- [x] **Step 3: Manual browser verification**

Run the client against a test config with `alerts.deterrent.enabled = true` and a handful of manually-inserted rows in the SQLite stats DB (e.g. via `sqlite3 deterrent_stats.db "INSERT INTO deterrent_events (timestamp_utc, succeeded) VALUES (...)"`), then load `http://localhost:8080/training-progress` in a browser and confirm:
- The day/week toggle buttons switch the rendered SVG bars.
- Hovering a bar shows its `<title>` tooltip with the correct count.
- The failure count input changes how many entries appear in the failures panel without a network request (check the browser's network tab — no new `fetch` fires on input).
- With an empty stats DB, the "No corrections recorded yet." message shows and the status line reads "not configured" or "configured — healthy"/"configured — not operational" as appropriate.

- [x] **Step 4: Commit**

```bash
git add counter_cruiser/client/web/templates/training_progress.html
git commit -m "feat(deterrent-usage-stats): implement training-progress page JS (bucketing, SVG chart, failures panel)"
```

> **Note:** Step 3 (manual browser verification) was completed via the chrome-devtools MCP plugin against a standalone Flask instance wired to a real `DeterrentStatsStore`/SQLite DB seeded with the Step 2 worked example (3 today, 2 yesterday, 1 forty-days-ago). Confirmed: day view renders bars matching the traced counts (yesterday=2, today=3, rest 0, out-of-window event dropped) with correct `<title>` tooltips (accessible-name snapshot showed e.g. `"2026-07-11: 3"`); week view toggle re-renders into the expected 2 buckets; changing the failure-count input re-rendered the failures list with zero new entries in the network request list (no `fetch` fired); and a second run with an empty DB and `configured=False` showed "No corrections recorded yet." and the "not configured" status line. Verified 2026-07-11.

archived-with: 2026-07-11-deterrent-usage-stats
---

### Task 8: Dashboard summary + operational-status indicator

**Files:**
- Modify: `counter_cruiser/client/web/templates/dashboard.html`
- Test: `tests/client/web/test_routes_dashboard.py` (extend `TestDashboardPage`)

**Interfaces:**
- Consumes: `GET /api/deterrent-stats` (same endpoint as Task 7's page — design.md explicitly rejects a second endpoint).
- Produces: nothing consumed by later tasks.

Per design.md: the dashboard route (`routes_dashboard.py`) itself needs **no** Python change — only the template gains a section that fetches the existing `/api/deterrent-stats` endpoint. The test only needs to confirm the static markup (link + summary container) is present in the served HTML; the "this week"/"last week" JS computation is exercised the same way as Task 7 (structural review, no JS test runner), scoped small here since it reuses Task 7's `isoWeekKey`/`dayKey` logic conceptually but does not need to duplicate the full bucketing implementation — it only needs a current-ISO-week count.

- [x] **Step 1: Write the failing test**

Add to `tests/client/web/test_routes_dashboard.py`, inside `class TestDashboardPage:`:

```python
    def test_dashboard_page_includes_training_progress_link(self) -> None:
        client, _ = _client()
        response = client.get('/')
        assert b'/training-progress' in response.data

    def test_dashboard_page_includes_deterrent_summary_section(self) -> None:
        client, _ = _client()
        response = client.get('/')
        assert b'deterrent-summary' in response.data
```

- [x] **Step 2: Run test to verify it fails**

Run: `pytest tests/client/web/test_routes_dashboard.py::TestDashboardPage -v`
Expected: FAIL — neither `/training-progress` nor `deterrent-summary` appear in the current `dashboard.html` output.

- [x] **Step 3: Write minimal implementation**

Modify `counter_cruiser/client/web/templates/dashboard.html`: add a new section after the existing `<section id="alerts">` block and before the `<p><a href="{{ url_for('calibrate') }}">` line:

```html
  <section id="deterrent-summary">
    <h2>Training Progress</h2>
    <p>Deterrent: <span id="deterrent-summary-status">loading…</span></p>
    <p>This week: <span id="deterrent-summary-count">0</span> corrections</p>
    <p><a href="{{ url_for('training_progress') }}">View full training progress</a></p>
  </section>
```

Add to the existing `<script>` block, inside `poll()` (after the existing alerts-fetch block, before its closing `}`):

```javascript
      const deterrentStats = await (await fetch('/api/deterrent-stats')).json();
      const statusEl = document.getElementById('deterrent-summary-status');
      if (!deterrentStats.configured) {
        statusEl.textContent = 'not configured';
      } else if (deterrentStats.operational) {
        statusEl.textContent = 'configured — healthy';
      } else {
        statusEl.textContent = 'configured — not operational';
      }
      const now = new Date();
      const startOfWeek = new Date(now);
      const dayNum = (startOfWeek.getDay() + 6) % 7;
      startOfWeek.setDate(startOfWeek.getDate() - dayNum);
      startOfWeek.setHours(0, 0, 0, 0);
      const thisWeekCount = deterrentStats.events.filter(
        (e) => new Date(e.timestamp_utc) >= startOfWeek
      ).length;
      document.getElementById('deterrent-summary-count').textContent = thisWeekCount;
```

Note: `url_for('training_progress')` requires the Flask view function in Task 6 be named `training_progress` (confirmed — see Task 6's `def training_progress():`).

- [x] **Step 4: Run test to verify it passes**

Run: `pytest tests/client/web/test_routes_dashboard.py -v`
Expected: PASS (all tests, including the two new ones)

- [x] **Step 5: Confirm 100% coverage**

Run: `pytest tests/client/web/test_routes_dashboard.py --cov=counter_cruiser.client.web.routes_dashboard --cov-report=term-missing`
Expected: 100% (the Python route itself is unchanged, so this reconfirms no regression)

- [x] **Step 6: Commit**

```bash
git add counter_cruiser/client/web/templates/dashboard.html tests/client/web/test_routes_dashboard.py
git commit -m "feat(deterrent-usage-stats): add deterrent usage summary to the dashboard"
```

archived-with: 2026-07-11-deterrent-usage-stats
---

### Task 9: Client integration — wire `DeterrentStatsStore` + `DeterrentStatus` into `main()`

**Files:**
- Modify: `counter_cruiser/client/__main__.py`
- Test: `tests/client/test_main.py` (extend)

**Interfaces:**
- Consumes: `DeterrentStatsStore(db_path: Path)` (Task 2), `DeterrentHandler(config, stats_store)` (Task 3), `DashboardState.set_deterrent_status` (Task 4), `create_app(state, settings, zone_store, stats_store)` (Task 5).
- Produces: nothing consumed by later tasks (this is the top-level wiring task).

This task threads the new store through `_build_alert_manager` (which currently constructs `DeterrentHandler(alerts.deterrent)`) and `main()` (which constructs `create_app` and must push `DeterrentStatus` before the web thread starts serving).

- [x] **Step 1: Write the failing tests**

Add to `tests/client/test_main.py`:

```python
class TestDeterrentStatsWiring:
    def test_deterrent_configured_and_operational_pushes_status(self, tmp_path) -> None:
        from counter_cruiser.config.models import AlertConfig, DeterrentConfig

        db_path = tmp_path / 'stats.db'
        config = ClientSettings(
            alerts=AlertConfig(
                deterrent=DeterrentConfig(
                    enabled=True, pin=17, stats_db_path=str(db_path)
                )
            )
        )
        real_state = DashboardState()

        with (
            patch('counter_cruiser.client.__main__._configure_logging'),
            patch(
                'counter_cruiser.client.__main__.load_client_config',
                return_value=config,
            ),
            patch('counter_cruiser.client.__main__.DashboardState', return_value=real_state),
            patch('counter_cruiser.client.__main__.OpenCVCapture'),
            patch('counter_cruiser.client.__main__.ClientSession') as session_cls,
            patch('counter_cruiser.client.__main__.signal.signal'),
            patch('counter_cruiser.client.__main__.asyncio.run'),
            patch('counter_cruiser.client.__main__.threading.Thread') as thread_cls,
            patch(
                'counter_cruiser.client.alerts.deterrent._import_gpio',
                return_value=None,  # forces is_operational=False deterministically
            ),
        ):
            thread_cls.return_value = MagicMock()
            session_cls.return_value.frame_height = config.frame_height

            main()

        status = real_state.get_deterrent_status()
        assert status.configured is True
        assert status.operational is False  # _import_gpio returns None above

    def test_deterrent_disabled_pushes_not_configured_status(self) -> None:
        config = ClientSettings()  # deterrent disabled by default
        real_state = DashboardState()

        with (
            patch('counter_cruiser.client.__main__._configure_logging'),
            patch(
                'counter_cruiser.client.__main__.load_client_config',
                return_value=config,
            ),
            patch('counter_cruiser.client.__main__.DashboardState', return_value=real_state),
            patch('counter_cruiser.client.__main__.OpenCVCapture'),
            patch('counter_cruiser.client.__main__.ClientSession') as session_cls,
            patch('counter_cruiser.client.__main__.signal.signal'),
            patch('counter_cruiser.client.__main__.asyncio.run'),
            patch('counter_cruiser.client.__main__.threading.Thread') as thread_cls,
        ):
            thread_cls.return_value = MagicMock()
            session_cls.return_value.frame_height = config.frame_height

            main()

        status = real_state.get_deterrent_status()
        assert status.configured is False
        assert status.operational is False
```

Also add a new test covering the deterrent-enabled path through `_build_alert_manager` (the pre-existing `TestBuildAlertManager` tests only cover the disabled-by-default and other-handlers-enabled cases; Step 3 below updates those two pre-existing tests for the new signature, and this new test adds deterrent-specific coverage):

```python
class TestBuildAlertManagerWithDeterrent:
    def test_deterrent_enabled_constructs_handler_with_stats_store(self, tmp_path) -> None:
        from counter_cruiser.client.__main__ import _build_alert_manager
        from counter_cruiser.client.deterrent_stats import DeterrentStatsStore
        from counter_cruiser.config.models import AlertConfig, DeterrentConfig

        config = ClientSettings(
            alerts=AlertConfig(
                deterrent=DeterrentConfig(enabled=True, pin=17)
            )
        )
        stats_store = DeterrentStatsStore(tmp_path / 'stats.db')
        with patch(
            'counter_cruiser.client.alerts.deterrent._import_gpio', return_value=None
        ):
            manager, deterrent = _build_alert_manager(config, stats_store)
        assert manager._deterrent is not None
        assert deterrent is not None
        assert deterrent.is_operational is False  # _import_gpio patched to None above
```

- [x] **Step 2: Run tests to verify they fail**

Run: `pytest tests/client/test_main.py -v`
Expected: FAIL — `TypeError: _build_alert_manager() takes 1 positional argument but 2 were given` (new test), and `AttributeError`/assertion failures on `get_deterrent_status()` defaults not being pushed (wiring tests), since `main()` does not yet call `set_deterrent_status` or construct a `DeterrentStatsStore`.

- [x] **Step 3: Write minimal implementation**

Modify `counter_cruiser/client/__main__.py`:

Add the import:

```python
from counter_cruiser.client.deterrent_stats import DeterrentStatsStore
```

Update `_build_alert_manager` to accept and thread through a stats store, and to return the constructed `DeterrentHandler` alongside the `AlertManager` — `main()` needs to read `is_operational` off it, and returning it directly (rather than reaching into `AlertManager`'s private `_deterrent` attribute) keeps that reachable without breaking encapsulation:

```python
def _build_alert_manager(
    config: ClientSettings, stats_store: DeterrentStatsStore
) -> tuple[AlertManager, DeterrentHandler | None]:
    """Construct the AlertManager from enabled handlers in *config*.

    Returns the manager alongside the constructed DeterrentHandler (or None
    if disabled) so callers can read its operational status without
    reaching into the manager's internals.
    """
    alerts = config.alerts
    deterrent = (
        DeterrentHandler(alerts.deterrent, stats_store)
        if alerts.deterrent.enabled
        else None
    )
    handlers = []
    if alerts.snapshot.enabled:
        handlers.append(SnapshotHandler(alerts.snapshot))
    if alerts.log.enabled:
        handlers.append(LogHandler(alerts.log))
    if alerts.notification.enabled:
        handlers.append(NotificationHandler(alerts.notification))
    manager = AlertManager(
        handlers=handlers, cooldown_seconds=alerts.cooldown_seconds, deterrent=deterrent
    )
    return manager, deterrent
```

Update `main()`: construct the stats store before `_build_alert_manager`, and push `DeterrentStatus` right after. Replace:

```python
def main() -> None:
    """Load configuration and run the client until interrupted."""
    _configure_logging()
    config = load_client_config()
    history = DetectionHistory()
    alert_manager = _build_alert_manager(config)

    dashboard_state = DashboardState()
    zone_store = ZoneStore(config, resolve_client_config_path())
    fps_tracker = _FpsTracker()
    web_app = create_app(dashboard_state, config, zone_store)
```

with:

```python
def main() -> None:
    """Load configuration and run the client until interrupted."""
    _configure_logging()
    config = load_client_config()
    history = DetectionHistory()
    stats_store = DeterrentStatsStore(Path(config.alerts.deterrent.stats_db_path))
    alert_manager, deterrent_handler = _build_alert_manager(config, stats_store)

    dashboard_state = DashboardState()
    dashboard_state.set_deterrent_status(
        configured=config.alerts.deterrent.enabled,
        operational=deterrent_handler.is_operational if deterrent_handler else False,
    )
    zone_store = ZoneStore(config, resolve_client_config_path())
    fps_tracker = _FpsTracker()
    web_app = create_app(dashboard_state, config, zone_store, stats_store)
```

Add the `Path` import at the top of the file (alongside the existing `datetime` import line):

```python
from pathlib import Path
```

This changes `_build_alert_manager`'s signature and return type, which affects `TestBuildAlertManager` in `test_main.py` — the two pre-existing tests `test_all_handlers_disabled_by_default` and `test_enabled_handlers_are_constructed` must now pass a `stats_store` argument (backed by a real `tmp_path`, since `DeterrentStatsStore` opens a SQLite file on construction) and unpack a tuple result. Update those two pre-existing tests:

```python
class TestBuildAlertManager:
    def test_all_handlers_disabled_by_default(self, tmp_path) -> None:
        from counter_cruiser.client.__main__ import _build_alert_manager
        from counter_cruiser.client.deterrent_stats import DeterrentStatsStore

        stats_store = DeterrentStatsStore(tmp_path / 'stats.db')
        manager, deterrent = _build_alert_manager(ClientSettings(), stats_store)
        assert manager._handlers == []
        assert manager._deterrent is None
        assert deterrent is None

    def test_enabled_handlers_are_constructed(self, tmp_path) -> None:
        from counter_cruiser.client.__main__ import _build_alert_manager
        from counter_cruiser.client.deterrent_stats import DeterrentStatsStore
        from counter_cruiser.config.models import (
            AlertConfig,
            LogConfig,
            NotificationConfig,
            SnapshotConfig,
        )

        config = ClientSettings(
            alerts=AlertConfig(
                log=LogConfig(enabled=True, file='alerts.log'),
                snapshot=SnapshotConfig(enabled=True),
                notification=NotificationConfig(enabled=True),
            )
        )
        stats_store = DeterrentStatsStore(tmp_path / 'stats.db')
        manager, deterrent = _build_alert_manager(config, stats_store)
        assert len(manager._handlers) == 3
        assert deterrent is None
```

Also update `TestMain.test_wires_session_and_runs` and `TestMainCallsAlertManagerCleanupOnShutdown.test_cleanup_called_after_run` (both currently patch nothing around `_build_alert_manager`'s return — the former calls `main()` directly with the real function, which now needs a filesystem-backed `stats_db_path`; `ClientSettings(zones=[zone])` in that test uses the default `stats_db_path = './deterrent_stats.db'`, which would write to the repo's working directory during tests). Fix by pointing `stats_db_path` at `tmp_path` in that test's config construction:

```python
        config = ClientSettings(
            zones=[zone],
            alerts=AlertConfig(deterrent=DeterrentConfig(stats_db_path=str(tmp_path / 'stats.db'))),
        )
```

(add `from counter_cruiser.config.models import AlertConfig, DeterrentConfig, ClientSettings, Zone` to that test file's imports if not already present — `ClientSettings` and `Zone` already are; add `AlertConfig`, `DeterrentConfig`).

Apply the same `stats_db_path` fix to `test_main_constructs_dashboard_state_and_starts_web_thread` and `TestMainCallsAlertManagerCleanupOnShutdown.test_cleanup_called_after_run` (both call `main()` with a bare `ClientSettings()` — update to `ClientSettings(alerts=AlertConfig(deterrent=DeterrentConfig(stats_db_path=str(tmp_path / 'stats.db'))))`, adding a `tmp_path` fixture parameter to each test method).

Apply the same fix to `TestWebServerThreading.test_video_feed_does_not_block_api_status`, which also calls `create_app` directly (needs a fourth `stats_store` argument):

```python
        from counter_cruiser.client.deterrent_stats import DeterrentStatsStore

        stats_store = DeterrentStatsStore(tmp_path / 'stats.db')
        app = create_app(state, config, zone_store, stats_store)
```

- [x] **Step 4: Run tests to verify they pass**

Run: `pytest tests/client/test_main.py -v`
Expected: PASS (all tests, including the new wiring tests and every updated pre-existing test)

- [x] **Step 5: Confirm 100% coverage**

Run: `pytest tests/client/test_main.py --cov=counter_cruiser.client.__main__ --cov-report=term-missing`
Expected: 100%

- [x] **Step 6: Commit**

```bash
git add counter_cruiser/client/__main__.py tests/client/test_main.py
git commit -m "feat(deterrent-usage-stats): wire DeterrentStatsStore and DeterrentStatus into main()"
```

archived-with: 2026-07-11-deterrent-usage-stats
---

### Task 10: Documentation — `CLAUDE.md` update

**Files:**
- Modify: `CLAUDE.md`

**Interfaces:**
- Consumes: nothing (documentation-only task).
- Produces: nothing (terminal task besides finalization).

- [x] **Step 1: Update the Architecture section**

In `CLAUDE.md`, in the `client/` bullet's `web/` description, add mention of the new modules. Find the existing text (approximately):

```
`web/` (`DashboardState` — injected,
  thread-safe UI state; `create_app` — Flask app factory; `mjpeg.py` —
  rate-limited MJPEG generator; `zone_store.py` — `ZoneStore`, zone CRUD
  with mtime-based optimistic concurrency and atomic TOML write-back;
  `routes_dashboard.py`/`routes_live_feed.py`/`routes_zones.py` — route
  registration; `templates/` — dashboard and calibration pages), `__main__.py`
```

Replace with:

```
`web/` (`DashboardState` — injected,
  thread-safe UI state, including deterrent operational status;
  `create_app` — Flask app factory; `mjpeg.py` —
  rate-limited MJPEG generator; `zone_store.py` — `ZoneStore`, zone CRUD
  with mtime-based optimistic concurrency and atomic TOML write-back;
  `routes_dashboard.py`/`routes_live_feed.py`/`routes_zones.py`/
  `routes_deterrent_stats.py` — route registration; `templates/` —
  dashboard, calibration, and training-progress pages), `deterrent_stats.py`
  (`DeterrentStatsStore` — SQLite-backed persistent recorder for deterrent
  trigger attempts, one fresh connection per access, WAL mode), `__main__.py`
```

Also update the `alerts/` bullet's `DeterrentHandler` mention to note the new responsibilities:

Find:

```
`DeterrentHandler` — GPIO button-press simulation on the existing ultrasonic trainer;
```

Replace with:

```
`DeterrentHandler` — GPIO button-press simulation on the existing ultrasonic trainer, exposing an `is_operational` status and recording each attempt's outcome via the injected `DeterrentStatsStore`;
```

- [x] **Step 2: Update the Commands section**

Update the "Run client" comment to mention the new page:

Find:

```
# Run client (also starts the web UI on http://<web_host>:<web_port>/, default 0.0.0.0:8080)
```

Replace with:

```
# Run client (also starts the web UI on http://<web_host>:<web_port>/, default
# 0.0.0.0:8080; includes /training-progress for deterrent usage history)
```

- [x] **Step 3: Commit**

```bash
git add CLAUDE.md
git commit -m "docs(deterrent-usage-stats): document DeterrentStatsStore and training-progress page"
```

archived-with: 2026-07-11-deterrent-usage-stats
---

### Task 11: Finalization — full suite, coverage, lint, docstrings

**Files:**
- No new files; verification-only task across everything touched by Tasks 1–10.

**Interfaces:**
- Consumes: the complete change from Tasks 1–10.
- Produces: nothing (terminal task).

- [x] **Step 1: Run the full test suite with coverage**

Run: `pytest --cov=counter_cruiser --cov-report=term-missing --cov-fail-under=100`
Expected: all tests pass; coverage report shows 100% (or the command fails and any gap must be closed with an additional test before proceeding — do not add `# pragma: no cover` to close a gap unless the line is genuinely unreachable, matching the existing codebase's sparing use of that marker on `_import_gpio`'s real-hardware branches).

- [x] **Step 2: Run ruff**

Run: `ruff check .`
Expected: no findings. If findings appear, fix them (e.g. wrap long lines, remove unused imports) and re-run.

Run: `ruff format .`
Expected: no files reformatted (or, if files are reformatted, re-run `pytest` afterward to confirm formatting didn't change behavior, then amend the affected task's commit — or add a small follow-up formatting commit).

- [x] **Step 3: Verify docstrings**

Manually confirm every new/modified public symbol has a docstring:
- `DeterrentConfig.stats_db_path` (field, no docstring needed — covered by the class docstring)
- `DeterrentStatsStore` and all its public methods (`__init__`, `record`, `recent_events`, `recent_failures`)
- `DeterrentHandler.is_operational`
- `DeterrentStatus` (dataclass) and `DashboardState.set_deterrent_status`/`get_deterrent_status`
- `register_deterrent_stats_routes`, `DeterrentStatsStoreProtocol` and its two methods
- `_build_alert_manager` (docstring already updated in Task 9)

Run: `grep -c '"""' counter_cruiser/client/deterrent_stats.py counter_cruiser/client/web/routes_deterrent_stats.py` to spot-check docstring presence (each public def/class should contribute one `"""..."""` pair).

- [x] **Step 4: Confirm no `print()` calls were introduced**

Run: `grep -rn "print(" counter_cruiser/client/deterrent_stats.py counter_cruiser/client/web/routes_deterrent_stats.py counter_cruiser/client/alerts/deterrent.py`
Expected: no output (no matches).

- [x] **Step 5: Verify the OpenSpec tasks.md checkboxes match delivered scope**

Re-read `openspec/changes/deterrent-usage-stats/tasks.md` section 3 ("Day/week bucketed retrieval") against what was actually built: this plan implements section 3 as `DeterrentStatsStore.recent_events(since_days)` returning raw events (Task 2), with **client-side** JS bucketing (Task 7), not server-side SQL `GROUP BY` day/week counts — per the design doc's explicit resolution overriding tasks.md's older wording. Confirm this reconciliation is intentional and does not need a tasks.md edit before checking off section 3's boxes (or edit tasks.md's wording to match, at the implementer's/coordinator's discretion, since editing OpenSpec artifacts is a build-phase-appropriate small spec adjustment per the project's comet-phase-guard rules).

- [x] **Step 6: Final commit (if any cleanup was needed in Steps 2–4)**

```bash
git add -A
git commit -m "chore(deterrent-usage-stats): finalize — ruff clean, 100% coverage confirmed"
```

(Skip this commit entirely if Steps 1–4 required no changes.)
