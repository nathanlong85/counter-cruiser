## 1. Persistent event store

- [x] 1.1 Write tests: recording an event persists it across a fresh connection (simulating restart); recorded events include timestamp and success flag; concurrent reads and writes (per design's WAL/per-access-connection approach) do not raise or corrupt data
- [x] 1.2 Implement a small SQLite-backed recorder (path resolved similarly to `SnapshotConfig.dir`/`LogConfig.file`) with WAL mode and a dedicated connection per access; no shared long-lived connection

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
