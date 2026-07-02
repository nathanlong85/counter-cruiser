# Subagent Progress Checkpoint — web-ui

Plan task: "Task 16: Finalization" (docs/superpowers/plans/2026-07-01-web-ui.md)
OpenSpec task mapping: "9.1-9.4 (full suite/coverage, ruff, docstrings, CLAUDE.md)" (openspec/changes/web-ui/tasks.md)
Stage: final-fix
Implementation commit: d5ba36d (final-review base)
RED/GREEN evidence: N/A pending fix
Review stages passed: final whole-branch review (opus) — Ready to merge: No (With fixes)
Unresolved feedback:
(1) CRITICAL: make_server() defaults threaded=False -> infinite /video_feed generator starves every other endpoint once a browser opens the dashboard. Fix: threaded=True.
(2) IMPORTANT: config.zones (ClientSettings.zones list) is shared mutable state crossing the asyncio/Flask thread boundary with no lock -- ZoneStore mutates it in place from the Flask thread while on_result/geometry/mjpeg read it from the asyncio thread. Contradicts design doc's "DashboardState is the only shared object" claim.
(3) IMPORTANT: DashboardState.record_alert is never called in production (on_result never records alerts) -- /api/alerts and dashboard alert history are permanently empty.
(4) IMPORTANT: update_stats(server_connected=True) is hardcoded and only called on successful detection results -- never set back to False on disconnect, so "Disconnected server is reflected" spec scenario cannot occur in practice.
Minor (5) FPS/status text not drawn on frame (only timestamp) and (6) session.get_frame called twice in on_result -- accepted, not blocking, to be recorded in tasks.md rationale.
Review-fix round: 1 (final-review round) — fix applied in 7c14adf, re-reviewed on opus, Ready to merge: Yes
Stage: done

## Completed
Task 1: complete (commits 9f1290d..a83dce0, review clean)
Task 2: complete (commits 8042656..d1de8e8, review clean)
Task 3: complete (commits a7c9d50..4de74d9, review clean)
Task 4: complete (commits 5ea5447..f598293, review clean)
Task 5: complete (commits 5aa6ccf..ddb09ea, review clean)
Task 6: complete (commits a9654af..2d864d9, review clean)
Task 7: complete (commits c1d74e3..56a0f3f, review clean)
Task 8: complete (commits a307ee0..d12a8f0, review clean)
Task 9: complete (commits 9133a95..1694b31, review clean)
Task 10: complete (commits 41e5eed..2d6cbc7, review clean)
Task 11: complete (commits b3117ab..0bfbdd2, review clean)
Task 12: complete (commits 13478a3..c227e0a, review clean)
Task 13: complete (commits 17d935d..9c4e8af, 1 fix round, review clean)
Task 14: complete (commits 226c02e..878ce19, review clean)
Task 15: complete (commits f13b238..ea98667, review clean)
