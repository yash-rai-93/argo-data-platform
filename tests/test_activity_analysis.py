"""Synthetic fixtures for period boundaries, attribution, and bounded backfills."""

from __future__ import annotations

import unittest
from datetime import UTC, date, datetime

from etl.refresh_activity import merge_events, plan_backfill
from transform.recent_activity import (
    activity_investigation,
    dates,
    snapshot_quality,
    weekly_comparison,
)


def event(identifier, day, actor="alice", repo="python/cpython", category="commit"):
    return {
        "event_id": identifier,
        "created_at": day + "T00:00:00+00:00",
        "actor_login": actor,
        "repo_name": repo,
        "event_type": "PushEvent",
        "event_category": category,
    }


def state(events=None, start="2026-10-01", end="2026-10-29", version=2):
    return {
        "schema_version": version,
        "coverage_start": start,
        "through_exclusive": end,
        "covered_days": dates(start, end),
        "refreshed_at": "2026-10-30T12:00:00+00:00",
        "events": events or [],
        "query": {"job_id": "synthetic-test"},
    }


class WeeklyTests(unittest.TestCase):
    def test_fourteen_consecutive_days_are_required(self):
        result = weekly_comparison(state(start="2026-10-16"))
        self.assertEqual(result["status"], "insufficient_coverage")
        self.assertEqual(result["days_needed"], 1)
        self.assertEqual(weekly_comparison(state(start="2026-10-15"))["status"], "ready")

    def test_missing_coverage_is_not_treated_as_zero_activity(self):
        snapshot = state()
        snapshot["covered_days"].remove("2026-10-20")
        with self.assertRaises(ValueError):
            weekly_comparison(snapshot)

    def test_zero_event_days_are_valid_and_no_zero_denominator_is_invented(self):
        snapshot = state()
        result = weekly_comparison(snapshot)
        self.assertEqual(result["current"]["events"], 0)
        self.assertIsNone(result["changes"]["events"]["percent"])
        self.assertEqual(snapshot_quality(snapshot)["zero_event_days"], 28)

    def test_windows_are_half_open_and_contributors_are_not_summed_across_repos(self):
        snapshot = state(
            [
                event("old", "2026-10-14"),
                event("before", "2026-10-15", "alice"),
                event("prior-end", "2026-10-21", "bob"),
                event("boundary", "2026-10-22", "alice"),
                event("same-actor", "2026-10-23", "alice", "numpy/numpy"),
                event("new", "2026-10-28", "carol", category="issue"),
            ]
        )
        result = weekly_comparison(snapshot)
        self.assertEqual(result["previous"]["events"], 2)
        self.assertEqual(result["current"]["events"], 3)
        self.assertEqual(result["current"]["active_contributors"], 2)
        self.assertEqual(result["returning_contributors"], 1)
        self.assertEqual(result["joining_this_period"], 1)
        self.assertEqual(result["absent_this_period"], 1)
        self.assertEqual(result["changes"]["events"]["percent"], 50)
        self.assertEqual(result["current"]["pr_issue_events"], 1)

    def test_repository_and_category_deltas_reconcile_including_rename(self):
        snapshot = state(
            [
                event("1", "2026-10-15", repo="tiangolo/fastapi"),
                event("2", "2026-10-22", repo="fastapi/fastapi"),
                event("3", "2026-10-23", repo="fastapi/fastapi", category="pull_request"),
            ]
        )
        result = weekly_comparison(snapshot)
        repos = result["repository_drivers"]
        self.assertEqual(len(repos), 1)
        self.assertEqual(repos[0]["name"], "fastapi/fastapi")
        for key in ("repository_drivers", "category_drivers"):
            self.assertEqual(sum(row["delta"] for row in result[key]), 1)

    def test_peak_investigation_handles_zero_days_and_missing_prior_day(self):
        empty = activity_investigation(state())
        self.assertIsNone(empty["peak_share_percent"])
        result = activity_investigation(state([event("1", "2026-10-01")]))
        self.assertIsNone(result["previous_day"])
        self.assertEqual(result["top_actor_events"], 1)
        self.assertEqual(result["peak_events_excluding_top_actor"], 0)

    def test_duplicate_retained_ids_fail_quality(self):
        with self.assertRaises(ValueError):
            snapshot_quality(state([event("1", "2026-10-22"), event("1", "2026-10-22")]))

    def test_quality_records_validation_without_claiming_freshness(self):
        result = snapshot_quality(state())
        self.assertEqual(result["status"], "pass")
        self.assertEqual(result["expected_days"], 28)
        self.assertNotIn("fresh", result)
        self.assertIsNone(result["last_query"])


class BackfillTests(unittest.TestCase):
    now = datetime(2026, 10, 24, tzinfo=UTC)
    end = date(2026, 10, 23)

    def test_bootstrap_requests_exactly_twenty_eight_days(self):
        window = plan_backfill(None, self.end, self.now)
        self.assertEqual(window.start, date(2026, 9, 25))
        self.assertEqual((window.end - window.start).days, 28)
        self.assertEqual(window.mode, "backfill")

    def test_existing_seven_days_are_extended_backwards_without_cursor_rollback(self):
        snapshot = state(start="2026-10-15", end="2026-10-22", version=1)
        window = plan_backfill(snapshot, self.end, self.now)
        self.assertEqual(window.coverage_start, date(2026, 9, 25))
        self.assertGreaterEqual(window.end.isoformat(), snapshot["through_exclusive"])
        merged = merge_events(
            [event("old", "2026-10-15")],
            [event("old", "2026-10-15"), event("new", "2026-09-25")],
            window,
        )
        self.assertEqual([e["event_id"] for e in merged], ["new", "old"])

    def test_prior_longer_coverage_is_preserved(self):
        snapshot = state(start="2026-09-01", end="2026-10-22")
        window = plan_backfill(snapshot, self.end, self.now)
        self.assertEqual(window.coverage_start, date(2026, 9, 1))

    def test_rollback_publication_lag_and_disconnected_ranges_are_refused(self):
        for snapshot, end in [
            (state(start="2026-10-15", end="2026-10-23"), date(2026, 10, 22)),
            (None, date(2026, 10, 24)),
            (state(start="2026-07-01", end="2026-07-08"), self.end),
        ]:
            with self.assertRaises(ValueError):
                plan_backfill(snapshot, end, self.now)

    def test_repeated_complete_backfill_is_a_noop(self):
        snapshot = state(start="2026-09-25", end="2026-10-23")
        self.assertIsNone(plan_backfill(snapshot, self.end, self.now))


if __name__ == "__main__":
    unittest.main()
