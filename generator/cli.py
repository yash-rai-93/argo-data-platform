"""CLI entry point for the Argo synthetic-event generator (`argo-gen`)."""

from __future__ import annotations

import argparse
from pathlib import Path

from generator.engine import DataGenerator


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="argo-gen", description="Generate synthetic Argo events as JSONL."
    )
    parser.add_argument("--users", type=int, default=1000, help="number of user journeys")
    parser.add_argument("--days", type=int, default=90, help="registration window, in days")
    parser.add_argument(
        "--output", type=Path, default=Path("data/raw/events.jsonl"), help="output .jsonl path"
    )
    parser.add_argument("--seed", type=int, default=None, help="seed for reproducible output")
    args = parser.parse_args()

    args.output.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with args.output.open("w", encoding="utf-8") as fh:
        for line in DataGenerator(seed=args.seed).generate(args.users, days=args.days):
            fh.write(line + "\n")
            count += 1

    print(f"Wrote {count} events for {args.users} users to {args.output}")


if __name__ == "__main__":
    main()
