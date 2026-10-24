"""Pilot billing guards, source validation, and atomic GCS publication."""

from __future__ import annotations

import copy
import gzip
import json
import sys
import tempfile
import types
import unittest
from datetime import UTC, date, datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

from etl import pilot_activity as pilot


def event(identifier="1", repository_id="81598961", day="2026-10-20"):
    return {
        "event_id": identifier,
        "repository_id": repository_id,
        "event_type": "PushEvent",
        "event_category": "commit",
        "repo_name": "python/cpython",
        "actor_login": "alice",
        "created_at": day + "T12:00:00Z",
    }


class PilotTests(unittest.TestCase):
    def setUp(self):
        self.scope, self.digest = pilot.load_scope()
        self.start, self.end = date(2026, 10, 16), date(2026, 10, 23)
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)

    def test_scope_is_500_unique_ids_and_preserves_24_existing_repos(self):
        self.assertEqual(len({r["repository_id"] for r in self.scope["repositories"]}), 500)
        self.assertEqual(
            sum(r["selection_group"] == "existing_scope" for r in self.scope["repositories"]), 24
        )
        self.assertEqual(len(self.digest), 64)

    def test_duplicate_scope_id_is_rejected(self):
        scope = copy.deepcopy(self.scope)
        scope["repositories"][1]["repository_id"] = scope["repositories"][0]["repository_id"]
        path = Path(self.temp.name) / "scope.json"
        path.write_text(json.dumps(scope))
        with self.assertRaisesRegex(ValueError, "unique"):
            pilot.load_scope(path)

    def test_90_day_plan_is_continuous_and_bounded(self):
        batches = pilot.plan(self.end, datetime(2026, 10, 24, tzinfo=UTC), 90)
        self.assertEqual(len(batches), 13)
        self.assertEqual(batches[0]["start"], "2026-07-25")
        self.assertEqual(batches[-1]["end_exclusive"], "2026-10-23")
        for left, right in zip(batches, batches[1:], strict=False):
            self.assertEqual(left["end_exclusive"], right["start"])

    def test_future_source_dates_and_invalid_windows_are_rejected(self):
        for days in (0, 91):
            with self.assertRaises(ValueError):
                pilot.plan(self.end, datetime(2026, 10, 24, tzinfo=UTC), days)
        with self.assertRaises(ValueError):
            pilot.plan(date(2026, 10, 24), datetime(2026, 10, 24, tzinfo=UTC))
        with self.assertRaises(ValueError):
            pilot.render_sql(self.start, date(2026, 10, 24))

    def test_sql_has_exact_tables_stable_scope_and_existing_metric_contract(self):
        sql = pilot.render_sql(date(2025, 12, 31), date(2026, 1, 2))
        self.assertIn("githubarchive.day.20251231", sql)
        self.assertIn("githubarchive.day.20260101", sql)
        self.assertNotIn("githubarchive.day.20260102", sql)
        self.assertIn("s.repository_id in unnest(@repository_ids)", sql)
        self.assertNotIn("python_repos", sql)
        self.assertNotIn("__", sql)
        self.assertIn("then 'pull_request'", sql)
        self.assertIn("and s.actor_login not like", sql)

    def test_disk_deduplication_reports_zero_days_and_inactive_repos(self):
        path, quality = pilot.materialize(
            [event(), event(), event("2", day="2026-10-21")],
            self.scope,
            self.start,
            self.end,
            Path(self.temp.name),
        )
        self.assertEqual(quality["event_count"], 2)
        self.assertEqual(quality["distinct_accounts"], 1)
        self.assertEqual(quality["duplicate_source_rows"], 1)
        self.assertEqual(len(quality["queried_days"]), 7)
        self.assertEqual(quality["queried_days"][0]["events"], 0)
        self.assertEqual(len(quality["repositories"]), 500)
        with gzip.open(path, "rt") as data:
            self.assertEqual(len(data.readlines()), 2)

    def test_conflicting_event_ids_fail_validation(self):
        conflicting = event()
        conflicting["actor_login"] = "bob"
        with self.assertRaisesRegex(ValueError, "Conflicting"):
            pilot.materialize(
                [event(), conflicting], self.scope, self.start, self.end, Path(self.temp.name)
            )

    def test_scope_date_category_and_timezone_are_validated(self):
        names = {r["repository_id"]: r["name"] for r in self.scope["repositories"]}
        for field, value in (
            ("repository_id", "999999999999999999"),
            ("created_at", "2026-10-23T00:00:00Z"),
            ("created_at", "2026-10-20T00:00:00"),
            ("event_category", "issue"),
            ("event_type", "UnknownEvent"),
        ):
            row = event()
            row[field] = value
            with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                pilot.validate_row(row, names, self.start, self.end)

    def test_renamed_repository_uses_id_and_preserves_source_name(self):
        names = {r["repository_id"]: r["name"] for r in self.scope["repositories"]}
        row = event()
        row["repo_name"] = "old-owner/old-name"
        result = pilot.validate_row(row, names, self.start, self.end)
        self.assertEqual(result["repo_name"], "python/cpython")
        self.assertEqual(result["source_repo_name"], "old-owner/old-name")

    def test_empty_extract_is_valid_covered_zero_activity(self):
        _, quality = pilot.materialize([], self.scope, self.start, self.end, Path(self.temp.name))
        self.assertEqual(quality["event_count"], 0)
        self.assertEqual(len(quality["queried_days"]), 7)

    def clouds(self, estimate=123):
        # Fake only cloud boundaries; materialization and validation stay real.
        bigquery = types.ModuleType("google.cloud.bigquery")
        bigquery.QueryJobConfig = lambda **kwargs: types.SimpleNamespace(**kwargs)
        bigquery.ArrayQueryParameter = lambda *args: args
        bigquery.Client = MagicMock()
        client = bigquery.Client.return_value.__enter__.return_value
        query = MagicMock()
        query.result.return_value = [event()]
        query.job_id, query.total_bytes_processed, query.total_bytes_billed = "job-1", 123, 128
        client.query.side_effect = [types.SimpleNamespace(total_bytes_processed=estimate), query]
        storage = types.ModuleType("google.cloud.storage")
        storage.Client = MagicMock()
        bucket = storage.Client.return_value.__enter__.return_value.bucket.return_value
        cloud = types.ModuleType("google.cloud")
        cloud.bigquery, cloud.storage = bigquery, storage
        google = types.ModuleType("google")
        google.cloud = cloud
        modules = {
            "google": google,
            "google.cloud": cloud,
            "google.cloud.bigquery": bigquery,
            "google.cloud.storage": storage,
        }
        return modules, client, bucket, storage

    def execute(self, **kwargs):
        return pilot.run(
            project="test-project",
            scope=self.scope,
            scope_hash=self.digest,
            start=self.start,
            end=self.end,
            **kwargs,
        )

    def test_dry_run_never_queries_data_or_touches_storage(self):
        modules, client, _, storage = self.clouds()
        with patch.dict(sys.modules, modules):
            report = self.execute()
        self.assertEqual(client.query.call_count, 1)
        self.assertTrue(client.query.call_args.kwargs["job_config"].dry_run)
        storage.Client.assert_not_called()
        self.assertEqual(report["estimated_bytes"], 123)

    def test_apply_refuses_missing_and_excessive_caps_before_cloud_access(self):
        for cap in (None, 0, -1, pilot.MAX_BYTES_BILLED + 1):
            with self.subTest(cap=cap), self.assertRaises(ValueError):
                self.execute(dry_run=False, cap=cap, bucket_name="bucket")

    def test_over_cap_or_missing_estimate_never_executes_data_query(self):
        for estimate in (None, 101):
            modules, client, _, storage = self.clouds(estimate)
            with patch.dict(sys.modules, modules), self.assertRaises(ValueError):
                self.execute(dry_run=False, cap=100, bucket_name="bucket")
            self.assertEqual(client.query.call_count, 1)
            storage.Client.assert_not_called()

    def test_storage_preflight_failure_precedes_paid_query(self):
        modules, client, bucket, _ = self.clouds()
        bucket.blob.return_value.upload_from_string.side_effect = PermissionError("denied")
        with patch.dict(sys.modules, modules), self.assertRaises(PermissionError):
            self.execute(dry_run=False, cap=200, bucket_name="bucket")
        self.assertEqual(client.query.call_count, 1)

    def test_manifest_is_last_and_all_uploads_use_generation_preconditions(self):
        modules, client, bucket, _ = self.clouds()
        with patch.dict(sys.modules, modules):
            report = self.execute(dry_run=False, cap=200, bucket_name="bucket")
        self.assertEqual(report["stage"], "validated")
        self.assertEqual(report["quality"]["event_count"], 1)
        self.assertEqual(client.query.call_args.kwargs["job_config"].maximum_bytes_billed, 200)
        names = [call.args[0] for call in bucket.blob.call_args_list]
        self.assertTrue(names[0].endswith("/started.json"))
        self.assertTrue(names[-1].endswith("/manifest.json"))
        for call in bucket.blob.return_value.upload_from_string.call_args_list:
            self.assertEqual(call.kwargs["if_generation_match"], 0)
        self.assertEqual(
            bucket.blob.return_value.upload_from_filename.call_args.kwargs["if_generation_match"], 0
        )

    def test_failed_event_upload_never_publishes_manifest(self):
        modules, _, bucket, _ = self.clouds()
        bucket.blob.return_value.upload_from_filename.side_effect = OSError("upload failed")
        with patch.dict(sys.modules, modules), self.assertRaises(OSError):
            self.execute(dry_run=False, cap=200, bucket_name="bucket")
        self.assertFalse(
            any(call.args[0].endswith("/manifest.json") for call in bucket.blob.call_args_list)
        )


if __name__ == "__main__":
    unittest.main()
