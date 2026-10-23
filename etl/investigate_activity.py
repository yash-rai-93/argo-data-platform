"""Reproduce descriptive activity findings from an approved local checkpoint.

Default output is JSON on stdout. No authentication, query, or retraining.
Use --output to retain a reviewable result beside an investigation.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from etl.refresh_activity import load_state
from transform.recent_activity import activity_investigation

_ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=_ROOT / "data")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    state = load_state(args.data_dir)
    if state is None:
        parser.error("An approved activity checkpoint is required.")
    result = {
        **activity_investigation(state),
        "state_sha256": hashlib.sha256(
            (args.data_dir / "recent-activity-state.json.gz").read_bytes()
        ).hexdigest(),
        "source_query": state["query"],
    }
    output = json.dumps(result, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(output, encoding="utf-8")
    else:
        print(output, end="")


if __name__ == "__main__":
    main()
