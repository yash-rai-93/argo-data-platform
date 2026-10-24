"""Backfill recovery, cumulative budget reservations and checkpoint concurrency."""

from __future__ import annotations

import copy
import sys
import types
import unittest
from datetime import date
from unittest.mock import MagicMock, patch

from etl import backfill_activity as backfill


class NotFound(Exception):
    pass


class Conflict(Exception):
    pass


class PreconditionFailed(Exception):
    pass


class MemoryStore:
    def __init__(self):
        self.state, self.generation = None, 0
        self.prefix, self.name = "backfills/test", "backfills/test/checkpoint.json"
        self.bucket = types.SimpleNamespace(name="test-bucket")
        self.fail_at = None
        self.saves = 0

    def load(self):
        return copy.deepcopy(self.state), self.generation

    def save(self, state, generation):
        self.saves += 1
        if self.fail_at == self.saves:
            raise OSError("interrupted")
        if generation != self.generation:
            raise PreconditionFailed("stale generation")
        self.generation += 1
        self.state = copy.deepcopy(state)
        return self.generation


def report_for(store, client, scope, scope_hash, pending, **kwargs):
    return {
        "stage": "validated",
        "window": pending["window"],
        "job_id": pending["job_id"],
        "scope_sha256": scope_hash,
        "bytes_billed": 40,
        "quality": {
            "event_count": 3,
            "queried_days": [{"events": 3}],
            "repositories": [{"events": 3}],
        },
    }


class BackfillTests(unittest.TestCase):
    def setUp(self):
        self.config = backfill.configuration("project", "scope", date(2026, 10, 23))
        self.store = MemoryStore()
        self.scope = {"repositories": []}
        self.client = MagicMock()
        self.estimate = patch.object(backfill, "estimate_batch", return_value=30).start()
        self.land = patch.object(backfill, "land_batch", side_effect=report_for).start()
        self.addCleanup(patch.stopall)

    def execute(self, **kwargs):
        options = {"total_cap": 2000, "batch_cap": 100, "apply": True, "max_batches": 3}
        options.update(kwargs)
        return backfill.execute(self.store, self.client, self.scope, self.config, **options)

    def test_dry_run_estimates_all_13_batches_without_writing_or_landing(self):
        report = self.execute(apply=False)
        self.assertEqual(len(report["remaining_batches"]), 13)
        self.assertEqual(report["estimated_remaining_bytes"], 390)
        self.assertEqual(self.store.saves, 0)
        self.land.assert_not_called()

    def test_bounded_run_then_resume_has_continuous_cursor(self):
        self.assertEqual(self.execute()["batches_completed"], 3)
        self.assertEqual(self.execute()["batches_completed"], 6)
        self.assertEqual(len({c["job_id"] for c in self.store.state["completed"]}), 6)
        self.assertEqual(
            self.store.state["completed"][3]["window"]["start"],
            self.store.state["completed"][2]["window"]["end_exclusive"],
        )

    def test_completed_backfill_is_a_noop(self):
        report = self.execute(max_batches=13)
        self.assertEqual(report["stage"], "complete")
        self.assertEqual(report["event_count"], 39)
        self.assertEqual(report["approved_through_exclusive"], "2026-10-23")
        self.assertFalse(report["production_published"])
        calls = self.land.call_count
        self.execute()
        self.assertEqual(calls, self.land.call_count)

    def test_over_estimate_stops_before_checkpoint_or_query(self):
        self.estimate.return_value = 101
        with self.assertRaisesRegex(ValueError, "estimate"):
            self.execute()
        self.assertEqual(self.store.saves, 0)
        self.land.assert_not_called()

    def test_cumulative_reservation_stops_before_exceeding_budget(self):
        with self.assertRaisesRegex(ValueError, "cumulative"):
            self.execute(total_cap=120)
        self.assertEqual(len(self.store.state["completed"]), 1)
        self.assertEqual(backfill.accounted(self.store.state), 40)
        self.assertEqual(self.land.call_count, 1)

    def test_upload_interruption_keeps_reservation_and_reuses_job_id(self):
        self.land.side_effect = OSError("upload interrupted")
        with self.assertRaises(OSError):
            self.execute()
        pending_id = self.store.state["pending"]["job_id"]
        self.assertEqual(backfill.accounted(self.store.state), 100)
        self.land.side_effect = report_for
        self.execute(max_batches=1)
        self.assertEqual(self.store.state["completed"][0]["job_id"], pending_id)
        self.assertEqual(self.estimate.call_count, 1)

    def test_failed_cursor_write_retries_same_completed_query(self):
        self.store.fail_at = 2
        with self.assertRaises(OSError):
            self.execute()
        pending_id = self.store.state["pending"]["job_id"]
        self.store.fail_at = None
        self.execute(max_batches=1)
        self.assertEqual(self.store.state["completed"][0]["job_id"], pending_id)

    def test_reservation_write_failure_prevents_paid_query(self):
        self.store.fail_at = 1
        with self.assertRaises(OSError):
            self.execute()
        self.land.assert_not_called()

    def test_pinned_settings_cannot_change_on_resume(self):
        self.execute(max_batches=1)
        with self.assertRaisesRegex(ValueError, "changed"):
            self.execute(total_cap=1999)
        changed = copy.deepcopy(self.config)
        changed["project"] = "other-project"
        with self.assertRaises(ValueError):
            backfill.validate_state(self.store.state, changed, 2000)

    def test_manifest_mismatch_never_advances_cursor(self):
        def bad(*args, **kwargs):
            report = report_for(*args, **kwargs)
            report["job_id"] = "wrong-job"
            return report

        self.land.side_effect = bad
        with self.assertRaisesRegex(ValueError, "manifest"):
            self.execute()
        self.assertEqual(self.store.state["completed"], [])
        self.assertIsNotNone(self.store.state["pending"])

    def test_failed_job_retry_retains_full_previous_reservation(self):
        self.land.side_effect = [
            None,
            report_for(
                None,
                None,
                None,
                "scope",
                {
                    "window": self.config["batches"][0],
                    "job_id": "placeholder",
                },
            ),
        ]
        self.execute(max_batches=1, retry_failed=True)
        self.assertEqual(backfill.accounted(self.store.state), 100)
        self.assertEqual(len(self.store.state["failed"]), 1)
        self.land.side_effect = report_for
        self.execute(max_batches=1)
        self.assertEqual(backfill.accounted(self.store.state), 140)

    def test_corrupt_checkpoint_is_rejected(self):
        state = backfill.initial_state(self.config, 2000)
        state["pending"] = {"window": {"start": "wrong"}, "cap": 100}
        with self.assertRaises(ValueError):
            backfill.validate_state(state, self.config, 2000)

    def test_two_writers_cannot_commit_same_generation(self):
        self.store.save(backfill.initial_state(self.config, 2000), 0)
        with self.assertRaises(PreconditionFailed):
            self.store.save(backfill.initial_state(self.config, 2000), 0)


class CloudBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.exceptions = types.ModuleType("google.api_core.exceptions")
        self.exceptions.NotFound = NotFound
        self.exceptions.Conflict = Conflict
        self.exceptions.PreconditionFailed = PreconditionFailed
        google = types.ModuleType("google")
        api_core = types.ModuleType("google.api_core")
        cloud = types.ModuleType("google.cloud")
        bigquery = types.ModuleType("google.cloud.bigquery")
        bigquery.ArrayQueryParameter = lambda *args: args
        bigquery.QueryJobConfig = lambda **kwargs: types.SimpleNamespace(**kwargs)
        google.api_core, google.cloud = api_core, cloud
        api_core.exceptions, cloud.bigquery = self.exceptions, bigquery
        patch.dict(
            sys.modules,
            {
                "google": google,
                "google.api_core": api_core,
                "google.api_core.exceptions": self.exceptions,
                "google.cloud": cloud,
                "google.cloud.bigquery": bigquery,
            },
        ).start()
        self.addCleanup(patch.stopall)
        self.pending = {
            "job_id": "argo_backfill_test",
            "cap": 100,
            "window": {"start": "2026-10-16", "end_exclusive": "2026-10-23"},
        }

    def test_existing_bigquery_job_is_reused_without_submission(self):
        client = MagicMock()
        job = backfill.get_or_submit(client, {}, self.pending)
        self.assertIs(job, client.get_job.return_value)
        client.query.assert_not_called()

    def test_old_missing_job_is_not_resubmitted(self):
        client = MagicMock()
        client.get_job.side_effect = NotFound()
        self.pending["reserved_at"] = "2020-01-01T00:00:00+00:00"
        with self.assertRaisesRegex(ValueError, "Old pending"):
            backfill.get_or_submit(client, {"repositories": []}, self.pending)
        client.query.assert_not_called()

    def test_committed_manifest_is_reused_without_accessing_bigquery(self):
        store = MagicMock()
        self.pending["prefix"] = "backfills/test/attempts/test"
        report = report_for(None, None, None, "scope", self.pending)
        store.read_json.return_value = (report, 1)
        client = MagicMock()
        result = backfill.land_batch(store, client, {}, "scope", self.pending)
        self.assertEqual(result, report)
        client.get_job.assert_not_called()
        client.query.assert_not_called()

    def test_missing_job_is_submitted_with_pinned_id_and_cap(self):
        client = MagicMock()
        client.get_job.side_effect = NotFound()
        backfill.get_or_submit(client, {"repositories": []}, self.pending)
        self.assertEqual(client.query.call_args.kwargs["job_id"], self.pending["job_id"])
        self.assertEqual(client.query.call_args.kwargs["job_config"].maximum_bytes_billed, 100)
        self.assertIsNone(client.query.call_args.kwargs["job_retry"])

    def test_duplicate_job_submission_reattaches(self):
        client = MagicMock()
        job = object()
        client.get_job.side_effect = [NotFound(), job]
        client.query.side_effect = Conflict()
        self.assertIs(backfill.get_or_submit(client, {"repositories": []}, self.pending), job)

    def test_checkpoint_reads_and_writes_pin_object_generation(self):
        bucket = MagicMock()
        blob = bucket.blob.return_value
        blob.generation = 9
        blob.download_as_bytes.return_value = b'{"pending": null}'
        store = backfill.Checkpoints(bucket, "backfills/test")
        self.assertEqual(store.load(), ({"pending": None}, 9))
        blob.download_as_bytes.assert_called_once_with(if_generation_match=9)
        store.save({"pending": None}, 9)
        self.assertEqual(blob.upload_from_string.call_args.kwargs["if_generation_match"], 9)

    def test_missing_checkpoint_uses_create_only_generation(self):
        bucket = MagicMock()
        bucket.blob.return_value.reload.side_effect = NotFound()
        store = backfill.Checkpoints(bucket, "backfills/test")
        self.assertEqual(store.load(), (None, 0))
        store.save({"pending": None}, 0)
        self.assertEqual(
            bucket.blob.return_value.upload_from_string.call_args.kwargs["if_generation_match"], 0
        )


if __name__ == "__main__":
    unittest.main()
