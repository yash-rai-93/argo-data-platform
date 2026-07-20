"""Ingest dbt run artifacts into the warehouse as governance metadata.

dbt already emits everything an auditor would ask for -- which models built,
which tests passed, how long each node took, when the run happened -- into
``target/run_results.json`` and ``target/manifest.json``. Most projects delete
those files. This script parses them into ``main.meta_dbt_runs`` so the API can
expose build health, test pass rates, and data freshness to the frontend
without any additional instrumentation.

Row counts are read live from the warehouse rather than from the artifacts,
because dbt-duckdb does not report ``rows_affected`` for table materialisations.

Run after every ``dbt build``:

    cd transform && uv run dbt build && cd ..
    uv run python -m etl.ingest_dbt_artifacts
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Final

import duckdb
import pandas as pd

_ROOT: Final[Path] = Path(__file__).resolve().parents[1]
_TARGET_DIR: Final[Path] = _ROOT / "transform" / "target"
_RUN_RESULTS: Final[Path] = _TARGET_DIR / "run_results.json"
_MANIFEST: Final[Path] = _TARGET_DIR / "manifest.json"
_DB_PATH: Final[Path] = _ROOT / "transform" / "argo.duckdb"
_TABLE: Final[str] = "main.meta_dbt_runs"


def read_artifact(path: Path) -> dict[str, Any]:
    """Load a dbt JSON artifact, failing loudly when the run never happened."""
    if not path.exists():
        raise SystemExit(f"{path} not found; run 'dbt build' in transform/ first.")
    return json.loads(path.read_text(encoding="utf-8"))


def relation_row_counts(nodes: dict[str, Any]) -> dict[str, int]:
    """Return the live row count of every materialised model and seed.

    Queried from DuckDB because dbt-duckdb reports no rows_affected for table
    materialisations. A node that failed to build reports -1 rather than
    silently reporting 0, which would be indistinguishable from an empty table.
    """
    counts: dict[str, int] = {}
    connection = duckdb.connect(str(_DB_PATH), read_only=True)
    try:
        for unique_id, node in nodes.items():
            if node.get("resource_type") not in {"model", "seed"}:
                continue
            relation = f"{node['schema']}.{node['name']}"
            try:
                (count,) = connection.execute(f"select count(*) from {relation}").fetchone()
                counts[unique_id] = int(count)
            except duckdb.Error:
                counts[unique_id] = -1
    finally:
        connection.close()
    return counts


def build_frame(run_results: dict[str, Any], manifest: dict[str, Any]) -> pd.DataFrame:
    """Flatten one dbt invocation into a row per executed node."""
    metadata: dict[str, Any] = run_results["metadata"]
    nodes: dict[str, Any] = {**manifest["nodes"], **manifest.get("sources", {})}
    counts: dict[str, int] = relation_row_counts(manifest["nodes"])

    generated_at: datetime = datetime.fromisoformat(metadata["generated_at"].replace("Z", "+00:00"))

    records: list[dict[str, Any]] = []
    for result in run_results["results"]:
        unique_id: str = result["unique_id"]
        node: dict[str, Any] = nodes.get(unique_id, {})
        records.append(
            {
                "invocation_id": metadata["invocation_id"],
                "run_at": generated_at,
                "dbt_version": metadata["dbt_version"],
                "unique_id": unique_id,
                "node_name": node.get("name", unique_id.split(".")[-1]),
                "resource_type": node.get("resource_type", "unknown"),
                "materialization": node.get("config", {}).get("materialized"),
                "file_path": node.get("original_file_path"),
                "status": result["status"],
                "execution_time": round(float(result["execution_time"]), 4),
                "failures": int(result["failures"] or 0),
                "message": result.get("message"),
                "row_count": counts.get(unique_id, -1),
            }
        )

    frame = pd.DataFrame.from_records(records)
    frame["run_elapsed_time"] = round(float(run_results["elapsed_time"]), 4)
    return frame


def persist(frame: pd.DataFrame) -> None:
    """Append this invocation to the run history, replacing any re-ingest.

    The table is history, not a snapshot: keeping every invocation is what makes
    build-time regression and test-flakiness visible over weeks.
    """
    connection = duckdb.connect(str(_DB_PATH))
    try:
        connection.register("dbt_runs_arrow", frame)
        connection.execute(
            f"create table if not exists {_TABLE} as select * from dbt_runs_arrow limit 0"
        )
        invocation_id: str = str(frame["invocation_id"].iloc[0])
        connection.execute(f"delete from {_TABLE} where invocation_id = ?", [invocation_id])
        connection.execute(f"insert into {_TABLE} select * from dbt_runs_arrow")
    finally:
        connection.close()


def main() -> None:
    """Parse the latest dbt artifacts and load them into the warehouse."""
    run_results: dict[str, Any] = read_artifact(_RUN_RESULTS)
    manifest: dict[str, Any] = read_artifact(_MANIFEST)

    frame: pd.DataFrame = build_frame(run_results, manifest)
    tests: pd.DataFrame = frame.loc[frame["resource_type"] == "test"]
    passed: int = int((tests["status"] == "pass").sum())

    print(f"Invocation:   {frame['invocation_id'].iloc[0]}")
    print(f"Run at:       {frame['run_at'].iloc[0]}")
    print(f"Nodes:        {len(frame)}")
    print(f"Tests passed: {passed}/{len(tests)}")
    print(f"Elapsed:      {frame['run_elapsed_time'].iloc[0]}s")
    for row in frame.loc[frame["resource_type"].isin(["model", "seed"])].itertuples():
        print(
            f"  {row.node_name:<38} {row.status:<8} "
            f"{row.execution_time:>7.3f}s  rows={row.row_count}"
        )

    persist(frame)
    print(f"Saved {_TABLE}")


if __name__ == "__main__":
    main()
