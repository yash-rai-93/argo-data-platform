"""Synthetic task tests; no Airflow service or cloud access."""

import hashlib
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from orchestration import community_tasks as tasks


class AirflowTaskTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        (self.root / "etl").mkdir()
        (self.root / "etl/incremental_community.py").touch()
        (self.root / "data").mkdir()
        (self.root / "data/community-source.json").write_text('{"synthetic": true}')
        python = self.root / "python"
        python.touch()
        env = patch.dict(
            os.environ,
            {
                "ARGO_CHECKOUT_ROOT": str(self.root),
                "ARGO_ETL_PYTHON": str(python),
                "GOOGLE_CLOUD_PROJECT": "synthetic-project",
                "GCS_BUCKET": "private-bucket",
            },
        )
        env.start()
        self.addCleanup(env.stop)
        git = patch.object(tasks.subprocess, "check_output", return_value="commit\n")
        git.start()
        self.addCleanup(git.stop)
        self.params = {
            "apply": False,
            "end_date": "2026-10-23",
            "maximum_bytes_billed": 0,
            "total_max_bytes_billed": 1000,
        }

    def prepare(self):
        return tasks.prepare(self.params, "manual/synthetic:run")

    def test_run_parameters_are_pinned_and_directory_is_sanitized(self):
        settings = self.prepare()
        self.assertEqual(self.prepare(), settings)
        self.assertEqual(len(Path(settings["directory"]).name), 64)
        self.params["total_max_bytes_billed"] = 2000
        with self.assertRaisesRegex(ValueError, "settings changed"):
            self.prepare()

    def test_apply_needs_a_cap_and_parameter_types_are_strict(self):
        for changes in (
            {"apply": True},
            {"maximum_bytes_billed": -1},
            {"apply": "true"},
            {"total_max_bytes_billed": True},
            {"maximum_bytes_billed": 1001},
        ):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                tasks.prepare({**self.params, **changes}, "synthetic")

    def test_default_estimate_cannot_execute_paid_query(self):
        settings = self.prepare()
        with patch.object(tasks, "execute", side_effect=AssertionError("query forbidden")):
            self.assertEqual(
                tasks.ingest(settings, {"stage": "estimate"})["stage"], "estimate_only"
            )
            self.assertEqual(tasks.ingest(settings, {"stage": "no_op"})["stage"], "no_op")
        with self.assertRaisesRegex(ValueError, "explicitly"):
            tasks.execute(settings, "apply")

    def test_failed_or_over_cap_estimate_prevents_apply(self):
        self.params.update(apply=True, maximum_bytes_billed=100)
        settings = self.prepare()
        with patch.object(tasks, "execute", side_effect=AssertionError("query forbidden")):
            for report in (
                {"stage": "failed"},
                {"stage": "estimate", "estimated_remaining_bytes": 101},
            ):
                with self.subTest(report=report), self.assertRaises(ValueError):
                    tasks.ingest(settings, report)

    def test_pointer_change_prevents_query(self):
        settings = self.prepare()
        (self.root / "data/community-source.json").write_text("changed")
        with patch.object(tasks.subprocess, "run") as command:
            with self.assertRaisesRegex(ValueError, "pointer changed"):
                tasks.execute(settings, "estimate")
        command.assert_not_called()

    def test_subprocess_has_pinned_dates_no_shell_and_bounded_timeout(self):
        settings = self.prepare()

        def command(args, **kwargs):
            self.assertEqual(args[args.index("--end-date") + 1], "2026-10-23")
            self.assertNotIn("--apply", args)
            self.assertNotIn("shell", kwargs)
            self.assertEqual(kwargs["timeout"], 1500)
            self.assertNotIn("GITHUB_RUN_ID", kwargs["env"])
            Path(args[args.index("--report") + 1]).write_text(json.dumps({"stage": "no_op"}))

        with patch.object(tasks.subprocess, "run", side_effect=command):
            self.assertEqual(tasks.execute(settings, "estimate"), {"stage": "no_op"})

    def test_verified_candidate_receipt_and_corrupt_assets(self):
        settings = self.prepare()
        directory = Path(settings["directory"]) / "candidate"
        directory.mkdir()
        summary, state = b"synthetic-summary", b"synthetic-packed-state"
        (directory / "recent-activity.json").write_bytes(summary)
        (directory / "recent-activity-state.json.gz").write_bytes(state)
        audit = {
            "summary_sha256": hashlib.sha256(summary).hexdigest(),
            "state_sha256": hashlib.sha256(state).hexdigest(),
            "event_count": 2,
            "through_exclusive": "2026-10-23",
        }
        (directory / "publication-audit.json").write_text(json.dumps(audit))
        checked = json.dumps({"events": 2, "end": "2026-10-23"})
        with patch.object(tasks.subprocess, "check_output", return_value=checked):
            receipt = tasks.verify(settings, {"stage": "complete"})
            self.assertEqual(receipt["stage"], "candidate_verified")
            self.assertFalse(receipt["published"])
            (directory / "recent-activity.json").write_bytes(b"corrupt")
            with self.assertRaisesRegex(ValueError, "checksum"):
                tasks.verify(settings, {"stage": "complete"})

    def test_incomplete_candidate_is_not_reported_as_published(self):
        settings = self.prepare()
        self.assertFalse(tasks.verify(settings, {"stage": "no_op"})["published"])
        with self.assertRaises(ValueError):
            tasks.verify(settings, {"stage": "in_progress"})


if __name__ == "__main__":
    unittest.main()
