"""Land real GitHub Archive events from BigQuery into the DuckDB warehouse.

Executes sql/bigquery/extract_python_contributor_events.sql against the
googarchive public dataset, pulls the result as an Arrow table, and registers
it into DuckDB zero-copy as ``main.raw_github_events``.

Requires Google Application Default Credentials:
    gcloud auth application-default login
"""

from __future__ import annotations

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
    if not _SQL_PATH.exists():
        raise FileNotFoundError(f"Extraction SQL not found at {_SQL_PATH}")
    return _SQL_PATH.read_text(encoding="utf-8")


def run_bigquery_extract(sql: str) -> pa.Table:
    """Execute the query in BigQuery and return the result as an Arrow table."""
    project = os.environ.get("GOOGLE_CLOUD_PROJECT")
    client = bigquery.Client(project=project) if project else bigquery.Client()

    job = client.query(sql)
    table = job.to_arrow()

    processed = job.total_bytes_processed or 0
    print(f"BigQuery scanned {processed / 1024**3:.2f} GiB")
    print(f"Fetched {table.num_rows} rows")
    return table


def land_to_duckdb(table: pa.Table) -> None:
    """Register the Arrow table and materialize it into the warehouse."""
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
        connection.unregister("github_events_arrow")
        connection.close()


def main() -> None:
    """Run the BigQuery extract and land the result into DuckDB."""
    sql = read_extraction_sql()
    table = run_bigquery_extract(sql)
    if table.num_rows == 0:
        raise SystemExit("Query returned zero rows; check the window and repo allow-list.")
    land_to_duckdb(table)


if __name__ == "__main__":
    main()
