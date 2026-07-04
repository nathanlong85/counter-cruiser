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
