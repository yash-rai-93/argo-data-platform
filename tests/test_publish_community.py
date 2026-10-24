"""Publication reads only approved, verified backfill manifests; fixtures are synthetic."""

from __future__ import annotations

import copy
import json
import tempfile
import unittest
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from etl import backfill_activity as backfill
from etl import pilot_activity as pilot
from etl import publish_community as publish


class PublicationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.scope, self.digest = pilot.load_scope()
        config = backfill.configuration("project", self.digest, date(2026, 10, 23))
        self.state = backfill.initial_state(config, 20000)
        self.manifests, self.objects = {}, {}
        self.prefix = "backfills/" + "a" * 64
        for i, window in enumerate(config["batches"]):
            folder = self.root / str(i)
            folder.mkdir()
            row = {
                "event_id": str(i),
                "repository_id": self.scope["repositories"][0]["repository_id"],
                "event_type": "PushEvent",
                "event_category": "commit",
                "actor_login": "same-account",
                "repo_name": self.scope["repositories"][0]["name"],
                "created_at": window["start"] + "T12:00:00Z",
            }
            packed, quality = pilot.materialize(
                [row],
                self.scope,
                date.fromisoformat(window["start"]),
                date.fromisoformat(window["end_exclusive"]),
                folder,
            )
            manifest_name = self.prefix + "/attempts/" + f"{i:032x}" + "/manifest.json"
            event_name = manifest_name.replace("manifest.json", "events.jsonl.gz")
            self.objects[event_name] = packed.read_bytes()
            self.manifests[manifest_name] = {
                "window": window,
                "job_id": f"job-{i}",
                "stage": "validated",
                "scope_sha256": self.digest,
                "bytes_billed": 100,
                "bytes_processed": 90,
                "quality": quality,
                "events_uri": "gs://bucket/" + event_name,
            }
            self.state["completed"].append(
                {
                    "window": window,
                    "cap": 200,
                    "bytes_billed": 100,
                    "job_id": f"job-{i}",
                    "manifest": manifest_name,
                    "event_count": 1,
                }
            )

        def blob(name):
            return SimpleNamespace(
                download_to_filename=lambda dest: Path(dest).write_bytes(self.objects[name])
            )

        self.store = SimpleNamespace(
            prefix=self.prefix,
            bucket=SimpleNamespace(name="bucket", blob=blob),
            read_json=lambda name: (self.manifests[name], 1),
        )

    def assemble(self):
        return publish.assemble(
            self.store, self.state, self.scope, self.digest, self.root / "output"
        )

    def test_full_union_has_exact_distinct_counts_and_90_day_coverage(self):
        audit = self.assemble()
        self.assertEqual(audit["event_count"], 13)
        self.assertEqual(audit["distinct_accounts"], 1)
        self.assertEqual(audit["query"]["bytes_billed"], 1300)
        summary = json.loads((self.root / "output/recent-activity.json").read_text())
        self.assertEqual(len(summary["daily"]), 90)
        self.assertIsNone(summary["quality"]["last_query"])
        self.assertEqual(summary["publication"]["selected_repositories"], 500)
        self.assertEqual(summary["publication"]["observed_repositories"], 1)

    def test_partial_backfill_is_rejected(self):
        self.state["completed"].pop()
        with self.assertRaisesRegex(ValueError, "complete"):
            self.assemble()

    def test_corrupt_compressed_object_is_rejected(self):
        name = next(iter(self.objects))
        self.objects[name] += b"corrupt"
        with self.assertRaisesRegex(ValueError, "checksum"):
            self.assemble()

    def test_manipulated_metrics_are_rejected(self):
        next(iter(self.manifests.values()))["quality"]["distinct_accounts"] = 2
        with self.assertRaisesRegex(ValueError, "reconcile"):
            self.assemble()

    def test_cross_bucket_uri_is_rejected(self):
        next(iter(self.manifests.values()))["events_uri"] = "gs://other-bucket/events.gz"
        with self.assertRaisesRegex(ValueError, "escaped"):
            self.assemble()

    def test_manifest_path_traversal_is_rejected(self):
        self.state["completed"][0]["manifest"] = "other/manifest.json"
        with self.assertRaisesRegex(ValueError, "escaped"):
            self.assemble()

    def test_scope_or_query_contract_change_is_rejected(self):
        self.state["config"] = copy.deepcopy(self.state["config"])
        self.state["config"]["query_contract_sha256"] = "wrong"
        with self.assertRaises(ValueError):
            self.assemble()

    def test_no_bigquery_client_is_needed(self):
        with patch.object(
            backfill, "estimate_batch", side_effect=AssertionError("query forbidden")
        ):
            self.assertEqual(self.assemble()["covered_days"], 90)


if __name__ == "__main__":
    unittest.main()
