# Comet Design Handoff

- Change: deterrent-usage-stats
- Phase: design
- Mode: compact
- Context hash: 0b8a4442ba0b3f6f4adcac4ae4130646575737ec9e16ff49ec0ca58a05f4d97f

Generated-by: comet-handoff.sh

OpenSpec remains the canonical capability spec. This handoff is a deterministic, source-traceable context pack, not an agent-authored summary.

## openspec/changes/deterrent-usage-stats/proposal.md

- Source: openspec/changes/deterrent-usage-stats/proposal.md
- Lines: 1-72
- SHA256: e4ce12f3d52abdf8679d47404431f057bf421fe4639d91bda279996ce384aa04

```md
## Why

There is currently no way to tell whether the dog is learning to stay off the
counter. Alert history in the web UI is in-memory, capped at 50 entries, and
lost on every client restart — useless for judging a trend over days or
weeks. Separately, if the deterrent's GPIO setup silently fails, nothing in
the client or web UI reveals it: `DeterrentHandler` logs a warning and
self-disables, but every subsequent trigger is a silent no-op. A flat "0
corrections this week" trend line would be genuinely ambiguous between "the
dog stopped jumping up" and "the hardware died three weeks ago."

## What Changes

- Persistently record every **attempted** deterrent trigger (GPIO pin driven
  HIGH, regardless of whether the burst itself later errors) with a
  timestamp and a success/failure flag, in a new SQLite database on the
  client. Unbounded retention — the data volume (one row per correction) is
  trivial even over years of use.
- Expose the deterrent handler's **operational status** (configured +
  enabled + GPIO setup succeeded) so the web UI can distinguish "not
  configured," "configured and healthy," and "configured but broken."
- Add a dedicated `/training-progress` web page showing corrections
  bucketed by day and week (a hand-rolled inline SVG bar chart, consistent
  with the existing web UI's zero-JS-dependency pattern), plus recent
  failure context if any attempts have errored.
- Add a brief usage summary (e.g. "this week: N corrections") to the
  existing dashboard page, linking to the full training-progress page.
- Explicitly **not** in scope: raw elevated-detection frequency independent
  of the deterrent (a different metric, deferred as a possible future
  change), usage stats for other alert handlers (snapshot/log/notification),
  and any new config flag to enable/disable tracking — it is gated by the
  existing `alerts.deterrent.enabled`, same as `DeterrentHandler` itself.

## Capabilities

### New Capabilities
- `deterrent-usage-stats`: persistent recording of deterrent trigger
  attempts (timestamp + success flag) in SQLite, day/week-bucketed
  retrieval, and a dedicated web page presenting the trend plus recent
  failure context.

### Modified Capabilities
- `deterrent-control`: `DeterrentHandler` gains an observable operational
  status (configured / healthy / broken) and records each trigger attempt's
  outcome for the new stats capability, in addition to its existing
  burst-and-cleanup behavior.
- `status-dashboard`: the dashboard page gains a brief deterrent-usage
  summary linking to the new training-progress page.

## Impact

- **Runs on**: the Pi/client, alongside the existing web UI and detection
  pipeline (same process as the `web-ui` change).
- **New code**: a small SQLite-backed recorder (likely
  `counter_cruiser/client/deterrent_stats.py` or similar), a new Flask
  route + template for `/training-progress`, and additions to
  `DeterrentHandler` (operational status, recording each trigger) and the
  dashboard page/route.
- **New dependency surface**: none beyond Python's stdlib `sqlite3` — no
  new third-party package, no new frontend dependency.
- **Concurrency**: the SQLite file is written from the asyncio-driven
  detection thread (via `DeterrentHandler.trigger()`) and read from the
  Flask thread(s) serving `/training-progress` — needs the same care
  `ZoneStore` got in the `web-ui` change (dedicated connections per access,
  WAL mode for concurrent read/write), not a single shared connection.
- **Depends on**: the `web-ui` change (Flask app, `DashboardState`,
  dashboard page) and the `alert-system` change (`DeterrentHandler`,
  `AlertManager`).
- **Quality gates** (unchanged, enforced): 100% coverage
  (`--cov-fail-under=100`), no module-level mutable state, dependency
  injection, logging facade (no `print()`), docstrings on public APIs, ruff
  clean.
```

## openspec/changes/deterrent-usage-stats/design.md

- Source: openspec/changes/deterrent-usage-stats/design.md
- Lines: 1-145
- SHA256: b6f844a392179853271467304cd0c3aa0926f3903b7ec07ce63d007e7614aced

[TRUNCATED]

```md
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
```

Full source: openspec/changes/deterrent-usage-stats/design.md

## openspec/changes/deterrent-usage-stats/tasks.md

- Source: openspec/changes/deterrent-usage-stats/tasks.md
- Lines: 1-40
- SHA256: b7b7992a6b1a0a0b472126b799a84c1f41fa97faeea00e161416d7f8d66f4020

```md
## 1. Persistent event store

- [ ] 1.1 Write tests: recording an event persists it across a fresh connection (simulating restart); recorded events include timestamp and success flag; concurrent reads and writes (per design's WAL/per-access-connection approach) do not raise or corrupt data
- [ ] 1.2 Implement a small SQLite-backed recorder (path resolved similarly to `SnapshotConfig.dir`/`LogConfig.file`) with WAL mode and a dedicated connection per access; no shared long-lived connection

## 2. Deterrent handler: operational status + recording

- [ ] 2.1 Write tests: `DeterrentHandler` reports operational after successful GPIO setup; reports not operational when GPIO unavailable/setup fails
- [ ] 2.2 Implement an `is_operational` read-only property on `DeterrentHandler`
- [ ] 2.3 Write tests: a successful trigger records a succeeded event; an erroring trigger records a failed event and still drives the pin LOW (existing requirement, must not regress)
- [ ] 2.4 Wire the event store into `DeterrentHandler.trigger()` to record each attempt's outcome

## 3. Day/week bucketed retrieval

- [ ] 3.1 Write tests: day-bucketed counts returned correctly across multiple days; week-bucketed counts returned correctly across multiple weeks; empty result (no events) does not error
- [ ] 3.2 Implement bucketed-count queries against the event store (day and week granularity)

## 4. Training-progress page

- [ ] 4.1 Write tests for a JSON endpoint (or the page's data source) returning bucketed counts, operational status, and recent-failure context
- [ ] 4.2 Implement the endpoint reading from the event store and `DashboardState`'s deterrent-status field
- [ ] 4.3 Write a test that the training-progress page is served, including the no-events-yet empty state
- [ ] 4.4 Implement the `/training-progress` page template: hand-rolled inline SVG bar chart for day/week counts, operational status indicator, recent-failure context

## 5. Dashboard summary

- [ ] 5.1 Write tests: dashboard page presents a brief usage summary and a link to the training-progress page; reflects "not configured" vs. "configured but broken" vs. healthy states
- [ ] 5.2 Extend the dashboard page/route with the summary and link

## 6. Client integration

- [ ] 6.1 Write a test that `main()` constructs the event store and pushes `DeterrentHandler.is_operational` (when a deterrent is configured) into `DashboardState` at startup
- [ ] 6.2 Wire the event store and operational-status push into `counter_cruiser/client/__main__.py`

## 7. Finalization

- [ ] 7.1 Run the full test suite; confirm 100% coverage on all new/modified code
- [ ] 7.2 Run `ruff check` and `ruff format`; resolve all findings
- [ ] 7.3 Verify docstrings on all public modules/classes/functions added or modified
- [ ] 7.4 Update root `CLAUDE.md` Architecture/Commands sections to document the new stats store and training-progress page
```

## openspec/changes/deterrent-usage-stats/specs/deterrent-control/spec.md

- Source: openspec/changes/deterrent-usage-stats/specs/deterrent-control/spec.md
- Lines: 1-32
- SHA256: 652b17e6b31d388eec2d01bd30244edf506f3aa922d767cf7733e95b67899f6a

```md
## ADDED Requirements

### Requirement: Expose operational status

The deterrent handler SHALL expose whether it is currently operational
(configured, enabled, and GPIO setup succeeded) so other components can
distinguish a healthy deterrent from one that silently disabled itself.

#### Scenario: Operational after successful GPIO setup

- **WHEN** the deterrent handler is constructed and GPIO setup succeeds
- **THEN** the handler reports itself as operational

#### Scenario: Not operational when GPIO is unavailable

- **WHEN** the deterrent handler is constructed and `RPi.GPIO` cannot be imported or GPIO setup fails
- **THEN** the handler reports itself as not operational

### Requirement: Record each trigger attempt's outcome

The deterrent handler SHALL record each attempted trigger's outcome
(succeeded or failed) for use by the deterrent usage-stats capability.

#### Scenario: A successful burst is recorded as succeeded

- **WHEN** a trigger's GPIO burst completes without error
- **THEN** the attempt is recorded as succeeded

#### Scenario: An erroring burst is recorded as failed

- **WHEN** a trigger's GPIO burst raises an error
- **THEN** the attempt is recorded as not succeeded, and the handler still drives the pin LOW as already required
```

## openspec/changes/deterrent-usage-stats/specs/deterrent-usage-stats/spec.md

- Source: openspec/changes/deterrent-usage-stats/specs/deterrent-usage-stats/spec.md
- Lines: 1-63
- SHA256: 58b6862d6459bcbab57a063f6b3276da22bdeef77bda5827e81c1f427d6f975f

```md
## ADDED Requirements

### Requirement: Persistent deterrent trigger recording

The system SHALL persistently record every attempted deterrent trigger with
a timestamp and whether the attempt succeeded. Recorded events SHALL survive
a client restart.

#### Scenario: Successful attempt is recorded

- **WHEN** the deterrent handler attempts a trigger and the GPIO burst completes without error
- **THEN** an event is recorded with the current timestamp and marked as succeeded

#### Scenario: Failed attempt is recorded

- **WHEN** the deterrent handler attempts a trigger and the GPIO burst raises an error
- **THEN** an event is recorded with the current timestamp and marked as not succeeded

#### Scenario: Recorded events survive a restart

- **WHEN** the client is restarted after deterrent trigger events were recorded
- **THEN** previously recorded events remain available after restart

### Requirement: Day and week bucketed usage retrieval

The system SHALL provide deterrent trigger counts bucketed by day and by
week, based on recorded events.

#### Scenario: Day-bucketed counts are returned

- **WHEN** recorded events exist across multiple days
- **THEN** the system returns trigger counts grouped by day

#### Scenario: Week-bucketed counts are returned

- **WHEN** recorded events exist across multiple weeks
- **THEN** the system returns trigger counts grouped by week

#### Scenario: No events yet returns an empty result without erroring

- **WHEN** no deterrent trigger events have been recorded
- **THEN** the bucketed retrieval returns an empty result without erroring

### Requirement: Training-progress web page

The web server SHALL serve a dedicated page presenting the day/week bucketed
deterrent usage trend, the deterrent's current operational status, and
recent failure context if any recorded attempts failed.

#### Scenario: Training-progress page is served

- **WHEN** a browser requests the training-progress page
- **THEN** the server returns an HTML page presenting the bucketed usage trend and the deterrent's operational status

#### Scenario: Page reflects the no-events-yet state gracefully

- **WHEN** the training-progress page is requested before any deterrent trigger has been recorded
- **THEN** the page renders without erroring and indicates no corrections have been recorded yet

#### Scenario: Page surfaces recent failures

- **WHEN** one or more recorded events are marked as not succeeded
- **THEN** the training-progress page presents recent failure context alongside the usage trend
```

## openspec/changes/deterrent-usage-stats/specs/status-dashboard/spec.md

- Source: openspec/changes/deterrent-usage-stats/specs/status-dashboard/spec.md
- Lines: 1-23
- SHA256: 549276bd696cb0816c66fbefd602cc0b39b524e30e56132c70c4e9853a0574da

```md
## ADDED Requirements

### Requirement: Deterrent usage summary on the dashboard

The dashboard page SHALL present a brief deterrent usage summary and a link
to the training-progress page, and SHALL reflect the deterrent's
operational status (not configured, configured and healthy, or configured
but broken).

#### Scenario: Dashboard shows a usage summary linking to the full page

- **WHEN** a browser requests the dashboard page
- **THEN** the page presents a brief deterrent usage summary and a link to the training-progress page

#### Scenario: Dashboard reflects an unconfigured deterrent

- **WHEN** the deterrent is not configured (disabled in configuration)
- **THEN** the dashboard indicates the deterrent is not configured, distinct from a health problem

#### Scenario: Dashboard reflects a broken deterrent

- **WHEN** the deterrent is configured and enabled but is not operational
- **THEN** the dashboard indicates the deterrent is configured but not currently operational
```

