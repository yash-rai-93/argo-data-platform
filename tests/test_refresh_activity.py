"""Checkpoint, billing, and failure tests for the manual recent-data path."""

from __future__ import annotations

import json
import tempfile
import unittest
from datetime import UTC, date, datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from etl import refresh_activity as refresh


def event(identifier="1", day="2026-10-20", actor="alice"):
    return {
        "event_id": identifier,
        "event_type": "PushEvent",
        "event_category": "commit",
        "actor_login": actor,
        "repo_name": "python/cpython",
        "created_at": f"{day}T12:00:00+00:00",
    }


def checkpoint(events=None, start="2026-10-16", end="2026-10-23"):
    return {
        "schema_version": 1,
        "coverage_start": start,
        "through_exclusive": end,
        "refreshed_at": "2026-10-24T12:00:00+00:00",
        "events": events or [],
        "query": {"job_id": "test"},
    }


class RefreshTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 10, 24, tzinfo=UTC)
        self.temporary = tempfile.TemporaryDirectory()
        self.directory = Path(self.temporary.name)
        self.addCleanup(self.temporary.cleanup)
        (self.directory / "recent-activity.json").write_text(
            json.dumps({"schema_version": 1, "status": "not_initialized"})
        )

    def test_bootstrap_is_recent_and_does_not_fill_the_2023_gap(self):
        window = refresh.plan_window(None, date(2026, 10, 23), self.now)
        self.assertEqual(window.start, date(2026, 10, 16))
        self.assertEqual(window.end, date(2026, 10, 23))

    def test_publication_lag_and_rollback_are_refused(self):
        for end in (date(2026, 10, 24), date(2026, 10, 22)):
            with self.assertRaises(ValueError):
                refresh.plan_window(checkpoint(), end, self.now)

    def test_same_cursor_is_a_noop(self):
        self.assertIsNone(refresh.plan_window(checkpoint(), date(2026, 10, 23), self.now))

    def test_increment_overlaps_two_days_and_caps_long_gaps(self):
        window = refresh.plan_window(
            checkpoint(start="2026-07-01", end="2026-07-10"),
            date(2026, 10, 23),
            self.now,
        )
        self.assertEqual(window.start, date(2026, 7, 8))
        self.assertEqual(window.end, date(2026, 8, 8))
        self.assertFalse(window.caught_up)

    def test_exact_daily_tables_cross_the_year_boundary(self):
        window = refresh.Window(
            date(2025, 12, 31),
            date(2026, 1, 2),
            date(2025, 12, 31),
            date(2026, 1, 2),
        )
        sql = refresh.render_sql(window)
        self.assertIn("githubarchive.day.20251231", sql)
        self.assertIn("githubarchive.day.20260101", sql)
        self.assertNotIn("githubarchive.day.20260102", sql)
        self.assertNotIn("2023*", sql)
        self.assertNotIn("__DAILY_TABLES__", sql)

    def test_upsert_deduplicates_retries_and_accepts_late_arrivals(self):
        window = refresh.Window(
            date(2026, 10, 21),
            date(2026, 10, 24),
            date(2026, 10, 16),
            date(2026, 10, 24),
        )
        old = [event("1", "2026-10-21")]
        new = [event("1", "2026-10-21"), event("2", "2026-10-22")]
        result = refresh.merge_events(old, new, window)
        self.assertEqual(len(result), 2)
        self.assertEqual(refresh.merge_events(result, new, window), result)

    def test_events_outside_query_range_fail(self):
        window = refresh.plan_window(None, date(2026, 10, 23), self.now)
        for row in (event(day="2026-10-23"), {**event(), "created_at": "2026-10-20"}):
            with self.assertRaises(ValueError):
                refresh.merge_events([], [row], window)

    def test_old_events_expire_without_losing_the_coverage_boundary(self):
        window = refresh.Window(
            date(2026, 10, 21),
            date(2026, 10, 24),
            date(2026, 1, 1),
            date(2026, 10, 24),
        )
        result = refresh.merge_events(
            [event("old", "2026-01-02"), event("new", "2026-10-20")], [], window
        )
        self.assertEqual([row["event_id"] for row in result], ["new"])

    def test_snapshot_roundtrip_and_tampering_detection(self):
        state = checkpoint([event()])
        refresh.save_snapshot(state, self.directory)
        self.assertEqual(refresh.load_state(self.directory), state)
        path = self.directory / "recent-activity.json"
        summary = json.loads(path.read_text())
        summary["event_count"] += 1
        path.write_text(json.dumps(summary))
        with self.assertRaises(ValueError):
            refresh.load_state(self.directory)

    def test_missing_state_never_implicitly_reinitializes(self):
        refresh.save_snapshot(checkpoint([event()]), self.directory)
        (self.directory / "recent-activity-state.json.gz").unlink()
        with self.assertRaises(ValueError):
            refresh.load_state(self.directory)

    def test_summary_zero_fills_days_and_counts_unique_contributors(self):
        state = checkpoint([event("1"), event("2")])
        summary = refresh.summarize(state, "hash")
        self.assertEqual(summary["event_count"], 2)
        self.assertEqual(summary["active_contributors"], 1)
        self.assertEqual(len(summary["daily"]), 7)
        self.assertEqual(summary["daily"][0]["events"], 0)

    def fake_bigquery(self, estimated=100):
        client = MagicMock()
        estimate = SimpleNamespace(total_bytes_processed=estimated)
        job = SimpleNamespace(
            job_id="new-job",
            total_bytes_processed=100,
            total_bytes_billed=100,
            result=lambda: [event()],
        )
        client.query.side_effect = [estimate, job]
        factory = MagicMock()
        factory.return_value.__enter__.return_value = client
        module = SimpleNamespace(Client=factory, QueryJobConfig=lambda **kw: SimpleNamespace(**kw))
        return client, patch.dict("sys.modules", {"google.cloud": SimpleNamespace(bigquery=module)})

    def call_refresh(self, **overrides):
        kwargs = {
            "project": "test-project",
            "location": "US",
            "state": None,
            "window": refresh.plan_window(None, date(2026, 10, 23), self.now),
            "directory": self.directory,
            "dry_run": False,
            "maximum_bytes_billed": 1000,
        }
        kwargs.update(overrides)
        return refresh.refresh(**kwargs)

    def test_dry_run_does_not_download_or_change_the_checkpoint(self):
        original = (self.directory / "recent-activity.json").read_bytes()
        client, mocked = self.fake_bigquery()
        with mocked:
            self.call_refresh(dry_run=True)
        self.assertEqual(client.query.call_count, 1)
        self.assertTrue(client.query.call_args.kwargs["job_config"].dry_run)
        self.assertEqual((self.directory / "recent-activity.json").read_bytes(), original)
        self.assertFalse((self.directory / "recent-activity-state.json.gz").exists())

    def test_over_budget_or_unknown_estimate_never_executes_data_query(self):
        for estimated in (2000, None):
            client, mocked = self.fake_bigquery(estimated)
            with mocked, self.assertRaises(ValueError):
                self.call_refresh()
            self.assertEqual(client.query.call_count, 1)
            self.assertIsNone(refresh.load_state(self.directory))

    def test_missing_or_excessive_cap_fails_before_authentication(self):
        for cap in (None, 0, -1, refresh.MAX_BYTES_BILLED + 1):
            with self.assertRaises(ValueError):
                self.call_refresh(maximum_bytes_billed=cap)

    def test_success_passes_the_cap_and_advances_the_cursor(self):
        client, mocked = self.fake_bigquery()
        with mocked:
            self.call_refresh()
        config = client.query.call_args.kwargs["job_config"]
        self.assertEqual(config.maximum_bytes_billed, 1000)
        state = refresh.load_state(self.directory)
        self.assertEqual(state["through_exclusive"], "2026-10-23")
        self.assertEqual(len(state["events"]), 1)

    def test_failed_query_keeps_the_last_good_files(self):
        refresh.save_snapshot(checkpoint([event()]), self.directory)
        before = {path.name: path.read_bytes() for path in self.directory.iterdir()}
        client, mocked = self.fake_bigquery()
        client.query.side_effect = [
            SimpleNamespace(total_bytes_processed=100),
            RuntimeError("missing source day / quota / query failure"),
        ]
        with mocked, self.assertRaises(RuntimeError):
            self.call_refresh()
        self.assertEqual(
            before, {path.name: path.read_bytes() for path in self.directory.iterdir()}
        )

    def test_all_zero_events_can_advance_after_a_successful_query(self):
        client, mocked = self.fake_bigquery()
        client.query.side_effect = [
            SimpleNamespace(total_bytes_processed=100),
            SimpleNamespace(
                job_id="empty",
                total_bytes_processed=100,
                total_bytes_billed=100,
                result=list,
            ),
        ]
        with mocked:
            self.call_refresh()
        state = refresh.load_state(self.directory)
        self.assertEqual(state["events"], [])
        self.assertEqual(state["through_exclusive"], "2026-10-23")


if __name__ == "__main__":
    unittest.main()
