---
comet_change: web-ui
role: technical-design
canonical_spec: openspec
archived-with: 2026-07-02-web-ui
status: final
---

# Web UI — Technical Design

## Context

This design elaborates the OpenSpec `web-ui` change (`openspec/changes/web-ui/`): a
browser-based dashboard, live feed, and zone editor served from the Pi/client
alongside the existing capture pipeline. See `proposal.md` and `design.md` in
that change for the full goals/non-goals and high-level decisions (Flask +
streaming response, injected `DashboardState`, polling over SocketIO, shared
`annotate_frame`). This document resolves the open questions that document
flagged, at implementation-ready detail.

## Threading Model

The client entrypoint (`counter_cruiser/client/__main__.py`) runs the capture
pipeline via `asyncio.run(session.run())` in the main thread. Flask's WSGI
server is synchronous and would block that loop if run inline, so the web
server runs in a **daemon thread** started from `main()` before entering the
asyncio loop:

```python
from werkzeug.serving import make_server

def _run_web_server(app: Flask, host: str, port: int) -> None:
    make_server(host, port, app).serve_forever()

web_thread = threading.Thread(
    target=_run_web_server, args=(app, config.web_host, config.web_port), daemon=True
)
web_thread.start()
```

No separate process, no IPC. The only object shared across the asyncio thread
(writer, via `on_result`) and the Flask thread (reader, via request handlers)
is the injected `DashboardState`; its internal lock is the sole
cross-thread contention point. `daemon=True` means the web thread never
blocks process shutdown; `session.stop()` on `SIGINT`/`SIGTERM` is unaffected.

## MJPEG Stream Rate

Bounded to a configurable default of **5 fps** — a spot-check feed, not smooth
video. New `ClientSettings` field:

```python
web_stream_fps: float = 5.0

@field_validator('web_stream_fps')
@classmethod
def positive_stream_fps(cls, v: float) -> float:
    if v <= 0:
        raise ValueError('web_stream_fps must be positive')
    return v
```

The MJPEG generator computes a minimum inter-frame interval (`1 / web_stream_fps`)
and sleeps to enforce it, using an injectable clock/sleep seam so tests can
bound iteration count deterministically (per `tasks.md` 6.1–6.3).

## Zone Write-Back: tomlkit

`counter_cruiser/config/loader.py` currently reads TOML via stdlib `tomllib`
(read-only). Zone edits from the web UI must persist back to the client TOML
file while preserving comments and unrelated settings (alert config, camera
settings, etc.) — stdlib `tomllib` cannot write, and a hand-rolled
section-splicing writer risks losing comments inside the zones block.

**Decision:** add `tomlkit` (pure-Python, format-preserving TOML
library) as a client dependency. The zone-writer module:

1. Loads the config file with `tomlkit.load` (preserves the whole document,
   including the optional `[counter_cruiser]` wrapper table used by
   `fixtures/client.toml`).
2. Replaces only the `zones` array-of-tables under that document with the
   updated zone set, serialized as tomlkit array-of-tables items.
3. Validates the resulting zone set through the existing `Zone` pydantic
   model before any write (rejected edits never touch the file).
4. Writes atomically: `tomlkit.dumps` to a temp file in the same directory,
   then `os.replace` (rename) onto the config path, so a crash mid-write
   cannot corrupt the file.

This satisfies `tasks.md` 7.5–7.6 exactly: valid edit persists and reloads
identically; rejected edit leaves the file untouched; write is atomic.

## Optimistic Concurrency Control

Zone edits (hand-edit vs. web-edit, or two browser tabs) are rare on a
single-household LAN tool, but should not silently clobber each other.

**Mechanism:** mtime-based optimistic concurrency, no locking:

- The get-zones endpoint (`tasks.md` 7.1–7.2) includes a `version` field in
  its response, computed as `os.stat(config_path).st_mtime_ns` at read time.
- Every create/edit/delete/toggle request body must include the `version` it
  read.
- Before writing, the handler re-stats the config file. If the current
  mtime does not equal the submitted `version`, the request is rejected with
  a conflict error (HTTP 409) and **no write occurs** — the client must
  re-fetch zones and retry.
- A successful write naturally changes the file's mtime, so the `version`
  returned by the *next* get-zones call reflects the new state.

No new persistent state is needed — the file's own mtime is the version
token, consistent with the "file remains source of truth" principle already
in `design.md`.

## Alert History Persistence

In-memory bounded deque only (as `design.md` already assumed), explicitly
**not** persisted or read from `alerts.log`. Lost on restart. Deterrent-usage
frequency (dog-training-progress tracking) is a plausible future feature but
out of scope for this change — noted here so it isn't rediscovered as a
"missing requirement" later.

## Testing Strategy

Unchanged from `design.md`/`tasks.md`: app-factory (`create_app(state,
settings) -> Flask`) exercised via Flask's `test_client()` against injected
fakes — no real camera, socket, or filesystem beyond temp files. Specific
additions from this design:

- MJPEG rate limiting: inject a fake clock/sleep to assert the generator
  enforces the configured interval without real-time waits.
- TOML write-back: exercise `tomlkit` round-trip against temp config files
  (valid edit / rejected edit / atomicity), plus the new version-mismatch
  case (stale `version` → conflict, no write, file byte-identical to before).
- `--cov-fail-under=100`, ruff clean, docstrings on public APIs, no `print()`
  (all carried over, unchanged).

## Spec Patch

`openspec/changes/web-ui/specs/zone-calibration/spec.md` gets two additions
(not a rewrite of scope/structure):

1. The "View current zones" requirement's scenarios gain a `version` field
   on returned zone data.
2. A new requirement, "Conflicting edit is rejected," with a scenario:
   a create/edit/delete/toggle request submitted with a stale `version` is
   rejected with a conflict error and does not modify the config file.

## Open Questions Resolved

All open questions from `design.md` are resolved by this document:
threading (daemon thread, no IPC), stream rate (5 fps default,
configurable), TOML write-back mechanism (`tomlkit`), alert history
(in-memory only, deterrent-usage stats deferred), and concurrency policy
(mtime-based optimistic concurrency, not plain last-writer-wins).
