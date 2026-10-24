"""Single-host Airflow task operations; credentials and event rows never enter XCom."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

LIMIT = 20_000_000_000


def prepare(params, run_id):
    root = Path(os.environ["ARGO_CHECKOUT_ROOT"]).resolve()
    python = Path(os.environ["ARGO_ETL_PYTHON"]).resolve()
    if not python.is_file() or not (root / "etl/incremental_community.py").is_file():
        raise ValueError("Configure an installed ETL Python and immutable ARGO checkout.")
    apply = params["apply"]
    cap, total = params["maximum_bytes_billed"], params["total_max_bytes_billed"]
    if type(apply) is not bool or type(cap) is not int or type(total) is not int:
        raise ValueError("Apply must be boolean; caps must be integer bytes.")
    if not 0 < total <= LIMIT or not 0 <= cap <= total or (apply and cap == 0):
        raise ValueError("Explicit bounded query caps are required before apply.")
    end = params["end_date"] or (datetime.now(UTC).date() - timedelta(days=1)).isoformat()
    date.fromisoformat(end)
    project, bucket = os.environ["GOOGLE_CLOUD_PROJECT"], os.environ["GCS_BUCKET"]
    if not project or not bucket or "/" in bucket:
        raise ValueError("Use an explicit project and bare private bucket name.")
    commit = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=root, text=True, timeout=30
    ).strip()
    pointer = (root / "data/community-source.json").read_bytes()
    key = hashlib.sha256(run_id.encode()).hexdigest()
    directory = root / "data/generated/airflow" / key
    directory.mkdir(parents=True, exist_ok=True)
    frozen = directory / "approved-pointer.json"
    settings = {
        "root": str(root),
        "python": str(python),
        "directory": str(directory),
        "commit": commit,
        "pointer_sha256": hashlib.sha256(pointer).hexdigest(),
        "end": end,
        "project": project,
        "bucket": bucket,
        "cap": cap,
        "total": total,
        "apply": apply,
    }
    config = directory / "settings.json"
    if config.exists() and json.loads(config.read_text()) != settings:
        raise ValueError("Run settings changed; do not clear preparation to change an active run.")
    frozen.write_bytes(pointer)
    config.write_text(json.dumps(settings), encoding="utf-8")
    return settings


def execute(settings, mode):
    if mode not in ("estimate", "apply"):
        raise ValueError("Unknown task mode.")
    if mode == "apply" and not settings["apply"]:
        raise ValueError("Apply was not explicitly selected.")
    root, directory = Path(settings["root"]), Path(settings["directory"])
    current = (root / "data/community-source.json").read_bytes()
    frozen = (directory / "approved-pointer.json").read_bytes()
    expected = settings["pointer_sha256"]
    if any(hashlib.sha256(value).hexdigest() != expected for value in (current, frozen)):
        raise ValueError("Approved pointer changed; start a fresh DAG run.")
    commit = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=root, text=True, timeout=30
    ).strip()
    if commit != settings["commit"]:
        raise ValueError("Checkout changed during the run.")
    report = directory / (mode + ".json")
    args = [
        settings["python"],
        "-m",
        "etl.incremental_community",
        "--project",
        settings["project"],
        "--bucket",
        settings["bucket"],
        "--pointer",
        str(directory / "approved-pointer.json"),
        "--end-date",
        settings["end"],
        "--total-max-bytes-billed",
        str(settings["total"]),
        "--output",
        str(directory / "candidate"),
        "--report",
        str(report),
    ]
    if mode == "apply":
        args += ["--apply", "--maximum-bytes-billed", str(settings["cap"])]
    env = {**os.environ, "GITHUB_SHA": settings["commit"]}
    # A native Airflow run must not fabricate a GitHub Actions run link.
    env.pop("GITHUB_RUN_ID", None)
    subprocess.run(args, cwd=root, env=env, check=True, timeout=1500)
    result = json.loads(report.read_text(encoding="utf-8"))
    if result["stage"] not in ("estimate", "no_op", "complete"):
        raise ValueError("Ingestion did not finish; inspect its durable GCS checkpoint.")
    return result


def ingest(settings, estimate):
    if estimate["stage"] == "no_op":
        return {"stage": "no_op"}
    if estimate["stage"] != "estimate":
        raise ValueError("A successful estimate is required before ingestion.")
    if not settings["apply"]:
        return {"stage": "estimate_only"}
    if estimate["estimated_remaining_bytes"] > settings["cap"]:
        raise ValueError("Estimate exceeds the explicit query cap.")
    return execute(settings, "apply")


def verify(settings, result):
    if result["stage"] in ("no_op", "estimate_only"):
        return {"stage": result["stage"], "published": False}
    if result["stage"] != "complete":
        raise ValueError("A complete candidate is required.")
    directory = Path(settings["directory"]) / "candidate"
    # Validate via the ETL interpreter, keeping Airflow's environment independent.
    code = (
        "import json,sys; from pathlib import Path; "
        "from etl.refresh_activity import load_state; "
        "s=load_state(Path(sys.argv[1])); "
        "print(json.dumps({'events':len(s['events']),'end':s['through_exclusive']}))"
    )
    checked = json.loads(
        subprocess.check_output(
            [settings["python"], "-c", code, str(directory)],
            cwd=settings["root"],
            text=True,
            timeout=120,
        )
    )
    audit = json.loads((directory / "publication-audit.json").read_text(encoding="utf-8"))
    for name, key in (
        ("recent-activity.json", "summary_sha256"),
        ("recent-activity-state.json.gz", "state_sha256"),
    ):
        if hashlib.sha256((directory / name).read_bytes()).hexdigest() != audit[key]:
            raise ValueError("Candidate checksum mismatch.")
    if checked["events"] != audit["event_count"] or checked["end"] != audit["through_exclusive"]:
        raise ValueError("Candidate audit does not reconcile.")
    return {
        "stage": "candidate_verified",
        "published": False,
        "events": checked["events"],
        "end_exclusive": checked["end"],
        "audit_path": str(directory / "publication-audit.json"),
        "publication_operation": "community-incremental-refresh",
        "requested_end": settings["end"],
        "maximum_bytes_billed": settings["cap"],
        "total_max_bytes_billed": settings["total"],
    }
