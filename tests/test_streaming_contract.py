"""Synthetic replay/sink fixtures; no broker, Spark or cloud credentials."""

import copy
import json
import tempfile
import unittest
from pathlib import Path

from etl import pilot_activity as pilot
from streaming.contract import Sink, envelope
from streaming.spark_replay import bind


class StreamingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.scope, self.digest = pilot.load_scope()
        repo = self.scope["repositories"][0]
        self.event = {
            "event_id": "synthetic-1",
            "event_type": "PushEvent",
            "event_category": "commit",
            "actor_login": "synthetic-account",
            "repo_name": repo["name"],
            "created_at": "2026-10-22T00:00:00+00:00",
        }
        self.value = envelope(
            self.event,
            repo["repository_id"],
            {
                "coverage_start": "2026-07-25",
                "through_exclusive": "2026-10-23",
            },
            "a" * 64,
            "synthetic-replay",
            "2026-10-25T00:00:00+00:00",
        )
        self.sink = Sink(self.root / "events.sqlite", {"scope": self.digest})

    def row(self, offset=0, value=None):
        return {
            "topic": "synthetic-topic",
            "partition": 0,
            "offset": offset,
            "key": "synthetic-1",
            "value": json.dumps(value or self.value),
            "event_day": "2026-10-22",
        }

    def count(self, table):
        with self.sink.connect() as db:
            return db.execute("select count(*) from " + table).fetchone()[0]

    def test_duplicate_replay_and_retry_after_commit_are_idempotent(self):
        receipt = self.sink.write(0, [self.row(), self.row(1)], self.scope)
        self.assertEqual(receipt["new_ids"], 1)
        self.assertEqual(receipt["duplicate_ids"], 1)
        self.assertEqual(self.sink.write(0, [self.row(), self.row(1)], self.scope), receipt)
        self.sink.write(1, [self.row(2)], self.scope)
        self.assertEqual(self.count("events"), 1)
        self.assertEqual(self.count("batches"), 2)

    def test_changed_batch_id_or_offset_content_is_rejected(self):
        self.sink.write(0, [self.row()], self.scope)
        with self.assertRaisesRegex(ValueError, "Batch ID"):
            self.sink.write(0, [self.row(1)], self.scope)
        changed = self.row()
        changed["value"] = "{}"
        with self.assertRaisesRegex(ValueError, "offset content"):
            self.sink.write(1, [changed], self.scope)

    def test_conflicting_event_rolls_back_entire_batch(self):
        self.sink.write(0, [self.row()], self.scope)
        value = copy.deepcopy(self.value)
        value["event"]["actor_login"] = "changed"
        with self.assertRaisesRegex(ValueError, "Conflicting"):
            self.sink.write(1, [self.row(1, value)], self.scope)
        self.assertEqual(self.count("events"), 1)
        self.assertEqual(self.count("messages"), 1)
        self.assertEqual(self.count("batches"), 1)

    def test_invalid_records_are_quarantined_without_events(self):
        bad = []
        for i, field in enumerate(("schema_version", "mode", "source_state_sha256")):
            value = copy.deepcopy(self.value)
            value[field] = "invalid"
            bad.append(self.row(i, value))
        malformed = self.row(4)
        malformed["value"] = "not json"
        bad.append(malformed)
        receipt = self.sink.write(0, bad, self.scope)
        self.assertEqual(receipt["invalid_rows"], 4)
        self.assertEqual(self.count("events"), 0)
        self.assertEqual(self.count("quarantine"), 4)

    def test_wrong_key_scope_category_and_timestamp_are_quarantined(self):
        rows = []
        for i, (field, value) in enumerate(
            (
                ("repository_id", "9999999999999"),
                ("event_category", "issue"),
                ("created_at", "invalid"),
                ("repo_name", "wrong/repository"),
            )
        ):
            message = copy.deepcopy(self.value)
            message["event"][field] = value
            rows.append(self.row(i, message))
        wrong_key = self.row(9)
        wrong_key["key"] = "different"
        rows.append(wrong_key)
        self.assertEqual(self.sink.write(0, rows, self.scope)["invalid_rows"], 5)

    def test_late_historical_events_keep_original_time(self):
        value = copy.deepcopy(self.value)
        value["event"]["created_at"] = "2026-07-25T00:00:00+00:00"
        row = self.row(value=value)
        row["event_day"] = "2026-07-25"
        self.assertEqual(self.sink.write(0, [row], self.scope)["new_ids"], 1)
        with self.sink.connect() as db:
            payload = json.loads(db.execute("select payload from events").fetchone()[0])
        self.assertEqual(payload["created_at"], "2026-07-25T00:00:00+00:00")

    def test_sink_and_checkpoint_identity_cannot_be_reused_silently(self):
        checkpoint, database = self.root / "cp", self.root / "bound.sqlite"
        contract = bind(checkpoint, database, "localhost:19092", "replay", self.digest)
        Sink(database, contract)
        self.assertEqual(
            bind(checkpoint, database, "localhost:19092", "replay", self.digest), contract
        )
        with self.assertRaises(ValueError):
            bind(checkpoint, database, "localhost:19092", "different-topic", self.digest)
        with self.assertRaises(ValueError):
            Sink(database, {"different": True})
        (checkpoint / "argo-contract.json").unlink()
        with self.assertRaisesRegex(ValueError, "Missing"):
            bind(checkpoint, database, "localhost:19092", "replay", self.digest)


if __name__ == "__main__":
    unittest.main()
