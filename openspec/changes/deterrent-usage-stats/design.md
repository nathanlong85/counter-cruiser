## Context

The `web-ui` change gave the client a Flask dashboard, but no persistent
history — `DashboardState`'s alert history is in-memory, capped at 50
entries, and explicitly documented as "lost on restart, deterrent-usage
frequency stats deferred as a future feature." This change delivers that
deferred feature: a persistent, queryable record of deterrent activity, so
the user can judge over weeks whether the dog is learning to stay off the
counter — and can tell that trend apart from a dead GPIO pin.

## Goals / Non-Goals

**Goals:**
- Persistently record every attempted deterrent trigger (timestamp +
  success/failure), surviving client restarts, with negligible storage cost.
- Expose whether the deterrent is currently operational (configured,
  enabled, GPIO setup succeeded) so a flat usage trend is interpretable.
- Present day/week-bucketed counts on a dedicated web page, plus a brief
  summary on the existing dashboard.
- Keep the zero-new-frontend-dependency pattern from `web-ui` — hand-rolled
  inline SVG for the bar chart.

**Non-Goals:**
- Raw elevated-detection frequency independent of the deterrent (a
  different metric; would need instrumenting `DetectionHistory`/`on_result`
  before cooldown suppression, not `AlertManager`). Deferred.
- Usage stats for other alert handlers (snapshot/log/notification).
- A config flag to enable/disable tracking — gated by the existing
  `alerts.deterrent.enabled`.
- Data pruning/retention limits — the data volume (one row per correction)
  is trivial even over years of daily use; no bound needed.

## Decisions

### SQLite for persistent storage

Use Python's stdlib `sqlite3` for a small, dedicated database recording one
row per deterrent trigger attempt (timestamp, success flag).

**Why:** No new third-party dependency (stdlib), file-based (fits the Pi 3B,
no server process), and its `GROUP BY`/date-function support makes day/week
bucketing a plain SQL query rather than hand-rolled aggregation code.
Storage volume is trivial for this data shape (a timestamp + a bool per
event), so no pruning logic is needed.

**Alternative considered:** parsing the existing `alerts.log`
(`LogHandler`'s output). Rejected — only produces data when `LogHandler` is
enabled (a separate, independent config toggle from the deterrent), and
free-form log parsing is more fragile than a purpose-built table.

### Recording point: inside `DeterrentHandler.trigger()`

Record the event where the GPIO burst is actually attempted, not in
`AlertManager` (which dispatches to all handlers generically and isolates
each one's exceptions). This keeps the deterrent-specific concern inside the
deterrent-specific module, consistent with the existing codebase's
separation (each alert handler owns its own behavior; `AlertManager` only
orchestrates cooldown and fan-out order).

**Why "attempted" not "confirmed success":** the pin is driven HIGH inside a
try/finally that always resets it LOW regardless of what happens in
between; "attempted" is the natural, already-isolated unit `trigger()`
already produces. The `succeeded` column captures whether the burst's
try block raised, without needing a success signal threaded back through
`AlertManager`'s isolated fan-out (which by design does not distinguish
handler outcomes from each other).

### Operational status: read once at startup, exposed via `DashboardState`

`DeterrentHandler._setup()` only runs once, in `__init__` — GPIO health does
not change at runtime except via that one-time setup outcome (a burst error
afterward doesn't change whether the pin/library are usable; it stays
`self._enabled` from setup). Expose a read-only `is_operational` property on
`DeterrentHandler`; `main()` pushes it into `DashboardState` once at
startup, alongside the existing `dashboard_state`/`zone_store` construction.
Distinguish "not configured" (`alerts.deterrent.enabled: false`, no
`DeterrentHandler` object at all) from "configured but broken"
(`DeterrentHandler` exists, `is_operational` is `False`) at the
`DashboardState`/route layer, since only `main()` knows whether a
`DeterrentHandler` was constructed at all.

### Concurrency: dedicated connections + WAL mode, no shared connection

The SQLite file is written from the asyncio-driven detection thread (via
`DeterrentHandler.trigger()`) and read from the Flask thread(s) serving
`/training-progress` and the dashboard summary (Flask now runs
`threaded=True`, per the `web-ui` fix). SQLite connections are not
thread-safe to share across threads by default.

**Decision:** open a fresh connection per access (write or read) rather than
holding one shared connection, and enable WAL (`PRAGMA journal_mode=WAL`) so
concurrent readers don't block the writer. This mirrors `ZoneStore`'s
pattern from `web-ui` (atomic operations, no long-lived shared mutable
handle) rather than introducing a new concurrency primitive.

**Alternative considered:** a single connection guarded by a
`threading.Lock` (matching `ZoneStore`'s zones-list lock). Rejected as
unnecessary complexity — SQLite's own WAL mode already handles concurrent
single-writer/multiple-reader access safely, and per-access connections
avoid holding a lock across potentially slow disk I/O.

### Hand-rolled inline SVG bar chart

No new JS charting library. The existing dashboard/calibration pages are
plain `fetch` + DOM manipulation with no build step and no static-asset
serving set up in Flask at all; day/week bucketed bar counts are simple
enough that an inline SVG generated server-side (or built client-side from
the JSON response, consistent with the existing pages' pattern) covers it
without introducing the project's first frontend dependency or a new
static-file-serving concern.

**Trade-off (explicit, not a slam dunk):** a real charting library would
give more headroom for richer visualizations later (zoom, tooltips,
multiple series). Accepted as a reasonable trade for staying dependency-free
now; revisit if the training-progress page's needs grow materially.

## Risks / Trade-offs

- **Ambiguous "0 corrections" trend** → Addressed directly by the
  operational-status signal; a flat trend is now always paired with a
  "deterrent: healthy/broken/not configured" indicator.
- **SQLite concurrent access on a Pi 3B** → WAL mode + per-access
  connections (see Decisions); if this proves insufficient under real
  usage, the fallback is a single writer-side connection with a lock,
  matching `ZoneStore`'s pattern.
- **Hand-rolled SVG chart quality/complexity** → Accepted trade-off (see
  Decisions); revisit with a real charting library if visualization needs
  grow.
- **New SQLite file needs a resolvable path** — likely a new config field
  (naming and default TBD in deep design), following the existing pattern
  of `SnapshotConfig.dir`/`LogConfig.file`.

## Migration Plan

Additive — no existing data to migrate. The SQLite database file is created
on first deterrent trigger (or at startup) if it doesn't exist. Rollback is
simply not recording/serving the new page; the existing alert-dispatch and
dashboard behavior is unaffected because this change only adds a new
recorder and new read-only routes.

## Open Questions

- Exact SQLite file path/config field naming.
- Exact bucket granularity on `/training-progress` (day-only, week-only, or
  both with a toggle?).
