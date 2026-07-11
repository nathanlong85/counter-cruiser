---
comet_change: deterrent-usage-stats
role: technical-design
canonical_spec: openspec
archived-with: 2026-07-11-deterrent-usage-stats
status: final
---

# Deterrent Usage Stats — Technical Design

## Context

This design elaborates the OpenSpec `deterrent-usage-stats` change
(`openspec/changes/deterrent-usage-stats/`): persistent recording of
deterrent trigger attempts, an operational-health signal for the deterrent,
and a training-progress web page. See `proposal.md` and `design.md` in that
change for the full goals/non-goals and high-level decisions (SQLite,
recording inside `DeterrentHandler.trigger()`, operational status read once
at startup). This document resolves the open questions that document
flagged, at implementation-ready detail.

## Configuration

Add one field to `DeterrentConfig` (`counter_cruiser/config/models.py`),
following the existing `SnapshotConfig.dir`/`LogConfig.file` pattern:

```python
class DeterrentConfig(BaseModel):
    ...
    stats_db_path: str = './deterrent_stats.db'
```

No new top-level config section, no new enable/disable flag — tracking is
gated by the existing `alerts.deterrent.enabled`.

## Storage: SQLite Schema and Access Pattern

One table, one row per attempted trigger:

```sql
CREATE TABLE IF NOT EXISTS deterrent_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp_utc TEXT NOT NULL,  -- ISO 8601, e.g. '2026-07-03T14:22:01.123456+00:00'
    succeeded INTEGER NOT NULL    -- 0 or 1
);
```

`timestamp_utc` is stored as ISO 8601 text (via `datetime.now(UTC).isoformat()`,
matching the existing `AlertHistoryEntry`/`annotate_frame` timestamp style)
rather than SQLite's numeric `julianday` — keeps the stored value
human-readable and trivially JSON-serializable without a conversion step.

**Access pattern** (mirrors `ZoneStore`'s established pattern from
`web-ui`): every read or write opens a fresh `sqlite3.connect(path)`,
enables WAL mode once per connection (`PRAGMA journal_mode=WAL`), performs
its operation, and closes. No shared long-lived connection, no
`threading.Lock` — WAL mode's single-writer/multiple-reader model already
handles the asyncio-thread-writes / Flask-thread-reads concurrency safely
without one.

```python
class DeterrentStatsStore:
    """SQLite-backed recorder for deterrent trigger attempts."""

    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path)
        conn.execute('PRAGMA journal_mode=WAL')
        return conn

    def _init_schema(self) -> None:
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
                'INSERT INTO deterrent_events (timestamp_utc, succeeded) VALUES (?, ?)',
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

ISO 8601 text timestamps sort correctly with a plain string comparison
(`>=`, `ORDER BY`), so no date-function gymnastics are needed for the
cutoff/ordering queries above.

**Implementation correction:** the code sample above, as written, leaks a
connection on every call — `with self._connect() as conn:` only
commits/rolls back the transaction on exit; it does not call
`conn.close()`. This was caught by task review during the build phase and
fixed in the actual implementation (`counter_cruiser/client/deterrent_stats.py`):
every method explicitly closes its connection in a `finally` block after the
`with conn:` block commits, e.g. `conn = self._connect(); try: ... finally: conn.close()`.
Harmless in practice today (CPython's GC closes the connection almost
immediately), but not a language guarantee, and worth doing correctly given
the target hardware (Pi 3B) — treat the code above as illustrative of the
query/schema shape only, not the exact connection-lifecycle code to copy.

## Recording Point: `DeterrentHandler.trigger()`

`DeterrentHandler` gains a `DeterrentStatsStore` constructed alongside its
existing GPIO setup, and records one event per `trigger()` call, wrapping
the existing try/finally burst logic:

```python
def trigger(self, context: AlertContext) -> None:
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
```

Note: a disabled handler (`not self._enabled or self._gpio is None`) returns
before recording anything — no event is written when the deterrent isn't
operational, consistent with "attempted" meaning a real GPIO attempt was
made, not merely that `trigger()` was called.

## Operational Status

Add a read-only property to `DeterrentHandler`:

```python
@property
def is_operational(self) -> bool:
    """Return whether GPIO setup succeeded and the handler is enabled."""
    return self._enabled
```

`main()` (`counter_cruiser/client/__main__.py`) pushes this into
`DashboardState` once at startup, alongside the existing
`dashboard_state`/`zone_store` construction:

```python
if alerts.deterrent.enabled:
    deterrent = DeterrentHandler(alerts.deterrent)
    dashboard_state.set_deterrent_status(configured=True, operational=deterrent.is_operational)
else:
    dashboard_state.set_deterrent_status(configured=False, operational=False)
```

`DashboardState` gains a small `DeterrentStatus` frozen dataclass
(`configured: bool`, `operational: bool`) and a `set_deterrent_status`/
`get_deterrent_status` pair, following the exact pattern of the existing
`set_server_connected`/`StatsSnapshot` methods (single lock acquisition, no
read-modify-write race).

## Data Endpoint: `GET /api/deterrent-stats`

New route module `counter_cruiser/client/web/routes_deterrent_stats.py`,
registered alongside the existing route modules in `app.py`:

```python
@app.get('/api/deterrent-stats')
def deterrent_stats():
    status = state.get_deterrent_status()
    events = stats_store.recent_events(since_days=182)
    failures = stats_store.recent_failures(limit=50)
    return jsonify({
        'configured': status.configured,
        'operational': status.operational,
        'events': [{'timestamp_utc': ts, 'succeeded': ok} for ts, ok in events],
        'recent_failures': failures,
    })
```

`since_days=182` and the `limit=50` failure cap are both named constants,
not magic numbers, matching the codebase's existing style (e.g.
`_DEFAULT_ALERT_HISTORY_CAPACITY` in `state.py`).

## Page: `GET /training-progress`

Server-side: `render_template('training_progress.html')`, no server-side
templating of the actual event data — the page's JS fetches
`/api/deterrent-stats` on load (same pattern as `dashboard.html`'s `poll()`
fetching `/api/status`/`/api/alerts`).

Client-side JS responsibilities:
1. Convert each event's `timestamp_utc` (ISO 8601, parses directly via
   `new Date(timestamp_utc)`) to the browser's local time.
2. **Day view:** bucket into local calendar days for the last 30 days;
   render as an inline SVG bar per day.
3. **Week view:** bucket into local ISO weeks (Monday-start) for the last
   26 weeks; render as an inline SVG bar per week. A toggle (two buttons or
   a `<select>`) switches between the two views; both are computed from the
   single fetched event list, no second fetch.
4. **Operational status:** render "not configured" / "configured — healthy"
   / "configured — not operational" based on `configured`/`operational`.
5. **Recent failures panel:** a fixed-height, `overflow-y: auto` `<div>`
   listing `recent_failures` (converted to local time), with a
   `<input type="number">` (default `5`) controlling how many of the
   fetched (up to 50) failures are rendered — client-side slice, no
   re-fetch when the input changes.

## Dashboard Summary

Extend the existing dashboard route/template
(`routes_dashboard.py`/`dashboard.html`) with a small section: fetches the
same `/api/deterrent-stats` endpoint (or a lighter-weight subset — reusing
the same endpoint is simpler and the payload is small, so no separate
summary-only endpoint is introduced), computes "this week" / "last week"
counts client-side from the returned events (same local-ISO-week bucketing
logic, shared as a small JS helper between the two pages), and shows the
operational status plus a link to `/training-progress`.

**Why reuse one endpoint instead of adding a lighter one:** the event
payload for 182 days at realistic usage volumes (a handful of corrections
per day at most) is at most a few hundred small JSON objects — trivial over
a LAN, not worth a second endpoint and duplicated status logic.

## Testing Strategy

- `DeterrentStatsStore`: write/read round-trip; a fresh store instance
  pointed at the same file after "restart" sees prior events (persistence);
  WAL mode confirmed via `PRAGMA journal_mode` readback; a threaded
  stress test (write from one thread while reading from another) does not
  raise or corrupt data, following the same test shape as `web-ui`'s
  `ZoneStore` concurrency test.
- `DeterrentHandler`: `is_operational` true after successful setup, false
  when GPIO unavailable/setup fails (extends existing
  `tests/client/alerts/test_deterrent.py`); a successful `trigger()` call
  records a `succeeded=True` event; an erroring burst records
  `succeeded=False` and still drives the pin LOW (regression guard on the
  existing "must not fire continuously" requirement); a disabled handler's
  `trigger()` records nothing.
- `DashboardState`: `DeterrentStatus`/`set_deterrent_status`/
  `get_deterrent_status` round-trip, defaults to
  `configured=False, operational=False`.
- Flask routes: `GET /api/deterrent-stats` returns the expected JSON shape
  against an injected fake `DeterrentStatsStore` and `DashboardState`;
  `GET /training-progress` is served, including the no-events-yet case.
- Dashboard summary: presents the link and reflects all three operational
  states (not configured / broken / healthy).
- Client wiring (`tests/client/test_main.py`): `main()` constructs the
  `DeterrentStatsStore` and pushes the correct `DeterrentStatus` into
  `DashboardState` at startup, for both the deterrent-configured and
  deterrent-disabled cases.
- `--cov-fail-under=100`, ruff clean, docstrings on public APIs, no
  `print()` (all carried over, unchanged).

## Open Questions Resolved

All open questions from `design.md` are resolved by this document: SQLite
file path/config field naming (`DeterrentConfig.stats_db_path`), and page
bucket granularity (both day and week views via a client-side toggle, local
time, from one shared 182-day raw-event fetch).
