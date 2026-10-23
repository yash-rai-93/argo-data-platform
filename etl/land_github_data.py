"""Land a cost-bounded historical GitHub Archive extract into DuckDB.

Authenticate using Application Default Credentials or the manual GitHub rebuild
workflow. A dry run estimates the scan without downloading or replacing data.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path

import duckdb
import pyarrow as pa
from google.cloud import bigquery

_ROOT = Path(__file__).resolve().parents[1]
_SQL_PATH = _ROOT / "sql" / "bigquery" / "extract_python_contributor_events.sql"
_DB_PATH = _ROOT / "transform" / "argo.duckdb"
_TARGET_TABLE = "main.raw_github_events"


def read_extraction_sql() -> str:
    """Return the BigQuery extraction query from disk."""
    return _SQL_PATH.read_text(encoding="utf-8")


def positive_bytes(value: str) -> int:
    """Parse an explicit positive bytes-billed limit."""
    try:
        limit = int(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("bytes-billed limit must be an integer") from error
    if limit <= 0:
        raise argparse.ArgumentTypeError("bytes-billed limit must be positive")
    return limit


def run_bigquery_extract(
    sql: str,
    *,
    project: str,
    location: str = "US",
    maximum_bytes_billed: int | None = None,
    dry_run: bool = False,
) -> pa.Table | None:
    """Estimate a scan or execute it with an explicit billing limit."""
    if not project:
        raise ValueError("An explicit BigQuery project is required.")
    if not dry_run and (maximum_bytes_billed is None or maximum_bytes_billed <= 0):
        raise ValueError("Extraction requires a positive maximum_bytes_billed limit.")

    config = bigquery.QueryJobConfig(dry_run=dry_run, use_query_cache=not dry_run)
    if not dry_run:
        config.maximum_bytes_billed = maximum_bytes_billed
    with bigquery.Client(project=project, location=location) as client:
        job = client.query(sql, job_config=config)
        if dry_run:
            print(f"Estimated scan: {job.total_bytes_processed or 0:,} bytes")
            print("Dry run only: no data downloaded or warehouse replaced.")
            return None
        table = job.to_arrow()
        print(f"BigQuery scanned {(job.total_bytes_processed or 0) / 1024**3:.2f} GiB")
        print(f"Fetched {table.num_rows} rows")
        return table


def land_to_duckdb(table: pa.Table) -> None:
    """Replace raw events only after a successful, nonempty extraction."""
    if table.num_rows == 0:
        raise ValueError("Query returned zero rows; existing warehouse was not changed.")
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    connection = duckdb.connect(str(_DB_PATH))
    try:
        connection.register("github_events_arrow", table)
        connection.execute(
            f"create or replace table {_TARGET_TABLE} as select * from github_events_arrow"
        )
        (landed,) = connection.execute(f"select count(*) from {_TARGET_TABLE}").fetchone()
        print(f"Landed {landed} rows into {_DB_PATH}::{_TARGET_TABLE}")
    finally:
        connection.close()


def main() -> None:
    """Parse extraction settings and refuse an uncapped execution."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", default=os.environ.get("GOOGLE_CLOUD_PROJECT"))
    parser.add_argument("--location", default=os.environ.get("BIGQUERY_LOCATION") or "US")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--maximum-bytes-billed",
        type=positive_bytes,
        default=os.environ.get("BIGQUERY_MAX_BYTES_BILLED") or None,
    )
    args = parser.parse_args()
    if not args.project:
        parser.error("set GOOGLE_CLOUD_PROJECT or pass --project")
    if not args.dry_run and args.maximum_bytes_billed is None:
        parser.error("review --dry-run, then set --maximum-bytes-billed explicitly")

    table = run_bigquery_extract(
        read_extraction_sql(),
        project=args.project,
        location=args.location,
        maximum_bytes_billed=args.maximum_bytes_billed,
        dry_run=args.dry_run,
    )
    if table is not None:
        land_to_duckdb(table)


if __name__ == "__main__":
    main()
