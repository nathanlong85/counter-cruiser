# Brainstorm Summary

- Change: web-ui
- Date: 2026-07-01

## Confirmed Technical Approach

- **Threading model:** Flask served via `werkzeug.serving.make_server` in a daemon thread launched from the client's `main()`, running alongside the existing asyncio capture loop in the main thread. No separate process, no IPC — the injected `DashboardState` object is the only shared state between threads, protected by an internal lock.
- **MJPEG stream rate:** Bounded to a configurable default of 5 fps (`ClientSettings.web_stream_fps: float = 5.0`, validated `> 0`). Explicitly not smooth video — a spot-check feed.
- **Zone write-back:** New `tomlkit` dependency (format-preserving TOML read/write). Mutate only the `[[zones]]` array-of-tables; comments and other settings elsewhere in the file are preserved untouched.
- **Concurrency control:** Optimistic concurrency via file mtime. The get-zones endpoint returns a `version` field (derived from `os.stat().st_mtime_ns`); every create/edit/delete/toggle request must include the `version` it read; the server re-stats the file before writing and rejects (no write) if the current mtime doesn't match the submitted version.
- **Alert history:** In-memory bounded deque only, lost on restart. Deterrent-usage-frequency stats (to track dog-training progress) explicitly deferred as a future feature — not in scope for this change.

## Key Trade-offs and Risks

- New `tomlkit` dependency — small, pure-Python, chosen over a hand-rolled writer because it fully solves comment/formatting preservation rather than accepting a known round-trip limitation.
- mtime-based OCC has coarse (sometimes second-level) resolution on some filesystems, but is sufficient for a low-frequency, single-household editing pattern (hand-edit vs. web-edit races are rare).
- In-memory-only alert history means a client restart loses recent-alert display in the dashboard — acceptable per user; revisit if usage-frequency stats become a real feature.
- Flask (WSGI, synchronous) in a background thread means the DashboardState lock is the only cross-thread contention point; keep update/read methods small and copy-on-read for frames to avoid tearing (already in design.md).

## Testing Strategy

Unchanged from design.md/tasks.md: app-factory + Flask `test_client()` exercised against injected fakes, no real camera/socket. Bounded/injectable MJPEG generator loop (clock/limit seam) so streaming tests terminate deterministically. TOML write-back tested against temp config files: valid edit persists and reloads identically, rejected edit leaves file untouched, write is atomic — now including a version-mismatch/conflict test (stale version → rejection, no write, config file unchanged). `--cov-fail-under=100`, ruff clean, docstrings on public APIs, no `print()`.

## Spec Patches

- `openspec/changes/web-ui/specs/zone-calibration/spec.md`: add one new requirement + acceptance scenario — "Conflicting edit is rejected" (a create/edit/delete/toggle request submitted with a stale `version` is rejected with a conflict error and does not modify the config file). Also add the `version` field to the "View current zones" requirement's returned zone data.
