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
