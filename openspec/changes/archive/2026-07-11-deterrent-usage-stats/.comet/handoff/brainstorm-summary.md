# Brainstorm Summary

- Change: deterrent-usage-stats
- Date: 2026-07-03

## Confirmed Technical Approach

- **Config:** `DeterrentConfig.stats_db_path: str = './deterrent_stats.db'`, following the existing `SnapshotConfig.dir`/`LogConfig.file` pattern.
- **Storage:** stdlib `sqlite3`, one `events` table (UTC timestamp, `succeeded` bool), WAL mode enabled, a fresh connection per access (write or read) — no shared long-lived connection, mirroring `ZoneStore`'s pattern from the `web-ui` change.
- **Recording point:** inside `DeterrentHandler.trigger()` — one row per attempt regardless of outcome ("attempted," not "confirmed success").
- **Operational status:** a read-only `is_operational` property on `DeterrentHandler` (configured + enabled + GPIO setup succeeded), read once at startup (setup only runs in `__init__`) and pushed into `DashboardState`. "Not configured" (no `DeterrentHandler` at all) is distinguished from "configured but broken" at the `main()`/route layer, since only `main()` knows whether a `DeterrentHandler` was constructed.
- **Data endpoint:** `GET /api/deterrent-stats` returns raw events from the last 182 days (UTC ISO8601 timestamp + `succeeded` flag), operational status, and a capped (last 50) recent-failures list.
- **Page:** `GET /training-progress`. Events are stored/transmitted in UTC but displayed in the browser's local time — bucketing (local calendar day for a 30-day view, local ISO week — Monday-start — for a 26-week view, user-toggled) happens client-side in JS, since the server cannot know the viewer's timezone without extra negotiation. Hand-rolled inline SVG bar chart, no new JS dependency, consistent with the existing dashboard/calibration pages.
- **Recent-failures panel:** scrollable, fixed-height container on the page, with a user-adjustable count input (default 5), sliced client-side from the already-fetched 50-event cap.
- **Dashboard summary:** brief usage text + link to `/training-progress` on the existing dashboard page, reflecting not-configured / broken / healthy deterrent states.

## Key Trade-offs and Risks

- UTC storage + client-side local-time bucketing avoids server-side timezone negotiation/config, at the cost of pushing bucketing logic into JS rather than a server-side SQL `GROUP BY`. Consistent with the existing dashboard's fetch-and-render pattern (no new architecture).
- The 50-event failure cap and 182-day fetch window are deliberate, generous simplifications — true unbounded history isn't paginated/shown, but isn't needed for this use case (a home training-progress view, not an analytics product).
- SQLite concurrent access (asyncio thread writes via `DeterrentHandler.trigger()`, Flask thread(s) read) handled via WAL mode + per-access connections, matching `ZoneStore`'s established pattern from `web-ui`.

## Testing Strategy

- Unit tests for the SQLite recorder: write/read round-trip, WAL mode, restart-persistence (reopening the file in a fresh connection), concurrent read/write access does not raise or corrupt data.
- `DeterrentHandler.is_operational` (operational after successful setup / not operational when GPIO unavailable) and outcome recording (successful burst → succeeded event; erroring burst → failed event, pin still driven LOW), extending the existing `tests/client/alerts/test_deterrent.py`.
- Flask route tests for `GET /api/deterrent-stats` and `GET /training-progress` via `create_app`/`test_client()` with injected fakes — no real GPIO, no real camera/socket.
- Dashboard summary tests: usage text + link present; not-configured vs. broken vs. healthy states reflected correctly.
- Client-wiring test in `tests/client/test_main.py`: `main()` constructs the event store and pushes `is_operational` into `DashboardState` at startup when a deterrent is configured.
- `--cov-fail-under=100`, ruff clean, docstrings on public APIs, no `print()` (all carried over, unchanged).

## Spec Patches

None. The existing delta specs (`deterrent-usage-stats`, `deterrent-control`, `status-dashboard`) already describe behavior at the right altitude (bucketed counts, page rendering, operational status) without prescribing server- vs. client-side bucketing, so this design fits without contradiction or need for amendment.
