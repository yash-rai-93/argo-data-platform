"""Synthetic incremental fixtures; no network, credentials, or paid queries."""

from __future__ import annotations

import copy
import hashlib
import json
import tempfile
import unittest
from datetime import UTC, date, datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from etl import backfill_activity as backfill
from etl import incremental_community as incremental
from etl import pilot_activity as pilot
from etl import refresh_activity as refresh


class IncrementalTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.scope, self.scope_hash = pilot.load_scope()
        self.repo = self.scope["repositories"][0]
        self.previous = {
            "schema_version": 2,
            "coverage_start": "2026-07-25",
            "through_exclusive": "2026-10-23",
            "covered_days": refresh.dates("2026-07-25", "2026-10-23"),
            "refreshed_at": "2026-10-24T00:00:00+00:00",
            "validated_at": "2026-10-24T00:00:00+00:00",
            "repositories": sorted(r["name"] for r in self.scope["repositories"]),
            "events": [
                self.event("expired", "2026-07-25"),
                self.event("kept", "2026-10-20"),
                self.event("overlap", "2026-10-21"),
            ],
            "query": {"kind": "backfill"},
        }
        self.config = self.plan(date(2026, 10, 24))
        self.checkpoint = backfill.initial_state(self.config, 1000)
        self.completed = {
            "window": self.config["batches"][0],
            "job_id": "job",
            "bytes_billed": 100,
            "cap": 200,
            "event_count": 3,
            "manifest": "incremental/" + "a" * 64 + "/attempts/" + "b" * 32 + "/manifest.json",
        }
        self.checkpoint["completed"] = [self.completed]
        self.rows = [
            self.row("overlap", "2026-10-21"),
            self.row("late", "2026-10-22"),
            self.row("new", "2026-10-23"),
        ]
        folder = self.root / "batch"
        folder.mkdir()
        packed, quality = pilot.materialize(
            self.rows, self.scope, date(2026, 10, 21), date(2026, 10, 24), folder
        )
        self.packed = packed.read_bytes()
        self.manifest = {
            "stage": "validated",
            "window": self.completed["window"],
            "job_id": "job",
            "scope_sha256": self.scope_hash,
            "quality": quality,
            "bytes_processed": 90,
            "bytes_billed": 100,
            "events_uri": "gs://bucket/"
            + self.completed["manifest"].replace("manifest.json", "events.jsonl.gz"),
        }
        self.store = SimpleNamespace(
            prefix="incremental/" + "a" * 64,
            bucket=SimpleNamespace(
                name="bucket",
                blob=lambda name: SimpleNamespace(
                    download_to_filename=lambda target: Path(target).write_bytes(self.packed)
                ),
            ),
            read_json=lambda name: (self.manifest, 1),
        )

    def event(self, identifier, day):
        return refresh.normalize_event(
            {
                "event_id": identifier,
                "created_at": day + "T12:00:00+00:00",
                "actor_login": "same-account",
                "repo_name": self.repo["name"],
                "event_type": "PushEvent",
                "event_category": "commit",
            }
        )

    def row(self, identifier, day):
        return {**self.event(identifier, day), "repository_id": self.repo["repository_id"]}

    def plan(self, end, state_hash="a" * 64):
        return incremental.configuration(
            "project",
            self.scope_hash,
            self.previous,
            state_hash,
            end,
            datetime(2026, 12, 1, tzinfo=UTC),
        )

    def approved_assets(self, state=None):
        state = state or self.previous
        packed = refresh.encode_state(state)
        digest = hashlib.sha256(packed).hexdigest()
        summary = refresh.summarize(state, digest)
        # Backfill publication has extra audit metadata outside serving metrics.
        summary["publication"] = {"kind": "backfill"}
        raw = json.dumps(summary).encode()
        base = incremental.RELEASE_BASE + "community-data-1-1/"
        pointer = {
            "schema_version": 1,
            "summary_url": base + "recent-activity.json",
            "state_url": base + "recent-activity-state.json.gz",
            "summary_sha256": hashlib.sha256(raw).hexdigest(),
        }
        assets = {pointer["summary_url"]: raw, pointer["state_url"]: packed}
        return pointer, assets

    def assemble(self):
        return incremental.assemble(
            self.store,
            self.checkpoint,
            self.previous,
            self.config,
            self.scope,
            self.root / "output",
        )

    def test_reads_approved_backfill_and_recomputes_metrics(self):
        pointer, assets = self.approved_assets()
        state, digest = incremental.load_approved(pointer, self.scope, fetch=assets.__getitem__)
        self.assertEqual(state, self.previous)
        self.assertEqual(digest, hashlib.sha256(assets[pointer["state_url"]]).hexdigest())

    def test_pointer_must_use_same_release_and_allowed_origin(self):
        pointer, _ = self.approved_assets()
        fetch = Mock(side_effect=AssertionError("network forbidden"))
        for url in ("https://other.example/state.gz", pointer["state_url"].replace("-1-1", "-2-1")):
            with self.subTest(url=url), self.assertRaisesRegex(ValueError, "same approved"):
                incremental.load_approved({**pointer, "state_url": url}, self.scope, fetch)
        fetch.assert_not_called()

    def test_corrupt_summary_or_state_is_rejected(self):
        for key in ("summary_url", "state_url"):
            pointer, assets = self.approved_assets()
            assets[pointer[key]] += b"corrupt"
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, "checksum"):
                incremental.load_approved(pointer, self.scope, assets.__getitem__)

    def test_bad_aggregate_with_valid_checksums_is_rejected(self):
        pointer, assets = self.approved_assets()
        summary = json.loads(assets[pointer["summary_url"]])
        summary["event_count"] += 1
        raw = json.dumps(summary).encode()
        assets[pointer["summary_url"]] = raw
        pointer["summary_sha256"] = hashlib.sha256(raw).hexdigest()
        with self.assertRaisesRegex(ValueError, "reconcile"):
            incremental.load_approved(pointer, self.scope, assets.__getitem__)

    def test_old_24_repository_sample_cannot_be_used(self):
        previous = copy.deepcopy(self.previous)
        previous["repositories"] = previous["repositories"][:24]
        pointer, assets = self.approved_assets(previous)
        with self.assertRaisesRegex(ValueError, "500-repository"):
            incremental.load_approved(pointer, self.scope, assets.__getitem__)

    def test_deduplicated_and_ordered_base_is_required(self):
        previous = copy.deepcopy(self.previous)
        previous["events"].append(previous["events"][0])
        packed = refresh.encode_state(previous)
        pointer, assets = self.approved_assets()
        summary = json.loads(assets[pointer["summary_url"]])
        summary["state_sha256"] = hashlib.sha256(packed).hexdigest()
        raw = json.dumps(summary).encode()
        assets[pointer["state_url"]] = packed
        assets[pointer["summary_url"]] = raw
        pointer["summary_sha256"] = hashlib.sha256(raw).hexdigest()
        with self.assertRaisesRegex(ValueError, "invalid"):
            incremental.load_approved(pointer, self.scope, assets.__getitem__)

    def test_promotion_requires_the_current_approved_predecessor(self):
        candidate = incremental.merge_snapshot(
            self.previous,
            self.rows,
            self.manifest["quality"],
            self.config,
            self.manifest,
            self.checkpoint,
        )
        with patch.object(
            incremental,
            "load_approved",
            side_effect=[(self.previous, "a" * 64), (candidate, "b" * 64)],
        ):
            self.assertEqual(incremental.validate_promotion({}, {}, self.scope), "2026-10-24")
        with (
            patch.object(
                incremental,
                "load_approved",
                side_effect=[(self.previous, "newer-approved-hash"), (candidate, "b" * 64)],
            ),
            self.assertRaisesRegex(ValueError, "Stale"),
        ):
            incremental.validate_promotion({}, {}, self.scope)

    def test_promotion_cannot_roll_back_coverage(self):
        candidate = copy.deepcopy(self.previous)
        candidate["through_exclusive"] = "2026-10-22"
        with (
            patch.object(
                incremental,
                "load_approved",
                side_effect=[(self.previous, "a" * 64), (candidate, "b" * 64)],
            ),
            self.assertRaisesRegex(ValueError, "roll back"),
        ):
            incremental.validate_promotion({}, {}, self.scope)

    def test_overlap_and_bounded_catchup(self):
        self.assertEqual(
            self.config["batches"],
            [{"start": "2026-10-21", "end_exclusive": "2026-10-24"}],
        )
        self.assertEqual(self.plan(date(2026, 11, 20))["batches"][0]["end_exclusive"], "2026-10-28")
        self.assertNotEqual(self.plan(date(2026, 10, 24), "b" * 64), self.config)

    def test_same_end_is_noop_and_rollback_or_unavailable_day_fails(self):
        self.assertIsNone(self.plan(date(2026, 10, 23)))
        with self.assertRaises(ValueError):
            self.plan(date(2026, 10, 22))
        with self.assertRaises(ValueError):
            incremental.configuration(
                "project",
                self.scope_hash,
                self.previous,
                "a" * 64,
                date(2026, 10, 24),
                datetime(2026, 10, 24, tzinfo=UTC),
            )

    def test_late_arrivals_overlap_expiration_and_exact_distinct_counts(self):
        original = copy.deepcopy(self.previous)
        audit = self.assemble()
        self.assertEqual(audit["event_count"], 4)
        self.assertEqual(audit["distinct_accounts"], 1)
        self.assertEqual(audit["coverage_start"], "2026-07-26")
        self.assertEqual(audit["covered_days"], 90)
        self.assertEqual(audit["selected_repositories"], 500)
        self.assertEqual(audit["quality_run"]["new_ids"], 2)
        self.assertEqual(audit["quality_run"]["overlap_ids"], 1)
        self.assertEqual(audit["quality_run"]["expired_ids"], 1)
        self.assertEqual(self.previous, original)
        state = refresh.load_state(self.root / "output")
        self.assertEqual(
            [e["event_id"] for e in state["events"]], ["kept", "overlap", "late", "new"]
        )
        summary = json.loads((self.root / "output/recent-activity.json").read_text())
        self.assertEqual(summary["quality"]["last_query"], audit["quality_run"])
        pointer, assets = self.approved_assets(state)
        self.assertEqual(
            incremental.load_approved(pointer, self.scope, assets.__getitem__)[0], state
        )

    def test_empty_successful_source_day_retains_previously_seen_overlap(self):
        state = incremental.merge_snapshot(
            self.previous,
            [],
            {"duplicate_source_rows": 0},
            self.config,
            self.manifest,
            self.checkpoint,
        )
        self.assertEqual([e["event_id"] for e in state["events"]], ["kept", "overlap"])
        self.assertEqual(len(state["covered_days"]), 90)

    def test_conflicting_id_fails_without_writing_outputs(self):
        self.rows[0]["actor_login"] = "changed-account"
        with self.assertRaisesRegex(ValueError, "Conflicting"):
            incremental.merge_snapshot(
                self.previous,
                self.rows,
                self.manifest["quality"],
                self.config,
                self.manifest,
                self.checkpoint,
            )
        self.assertFalse((self.root / "output").exists())

    def test_corrupt_landed_data_or_metrics_cannot_be_published(self):
        self.packed += b"corrupt"
        with self.assertRaisesRegex(ValueError, "checksum"):
            self.assemble()
        self.packed = self.packed[:-7]
        self.manifest["quality"]["distinct_accounts"] += 1
        with self.assertRaisesRegex(ValueError, "reconcile"):
            self.assemble()

    def test_query_must_complete_before_publication(self):
        self.checkpoint["completed"] = []
        with self.assertRaisesRegex(ValueError, "not complete"):
            self.assemble()

    def test_dry_run_does_not_save_or_submit_and_completed_rerun_does_not_query(self):
        state = backfill.initial_state(self.config, 1000)
        store = SimpleNamespace(
            load=lambda: (state, 0),
            save=Mock(),
            prefix="incremental/test",
            bucket=SimpleNamespace(name="bucket"),
            name="checkpoint.json",
        )
        with (
            patch.object(backfill, "estimate_batch", return_value=90),
            patch.object(
                backfill, "land_batch", side_effect=AssertionError("paid query forbidden")
            ),
        ):
            result = backfill.execute(
                store,
                Mock(),
                self.scope,
                self.config,
                total_cap=1000,
                batch_cap=None,
            )
        self.assertEqual(result["estimated_remaining_bytes"], 90)
        store.save.assert_not_called()
        store.load = lambda: (self.checkpoint, 1)
        with patch.object(
            backfill, "estimate_batch", side_effect=AssertionError("query forbidden")
        ):
            result = backfill.execute(
                store,
                Mock(),
                self.scope,
                self.config,
                total_cap=1000,
                batch_cap=200,
                apply=True,
            )
        self.assertEqual(result["stage"], "complete")
        store.save.assert_not_called()


if __name__ == "__main__":
    unittest.main()
