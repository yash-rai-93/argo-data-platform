"""Parse the real Airflow DAG in an isolated, version-pinned CI environment."""

import runpy
from pathlib import Path

dag = runpy.run_path(str(Path(__file__).resolve().parents[1] / "dags/community_refresh.py"))[
    "community_dag"
]
assert set(dag.task_ids) == {"prepare_run", "estimate", "ingest", "validate_candidate"}
assert dag.schedule is None
assert dag.catchup is False
assert dag.max_active_runs == 1
assert dag.params["apply"] is False
assert dag.params["maximum_bytes_billed"] == 0
assert dag.get_task("estimate").upstream_task_ids == {"prepare_run"}
assert dag.get_task("ingest").upstream_task_ids == {"prepare_run", "estimate"}
assert dag.get_task("validate_candidate").upstream_task_ids == {"prepare_run", "ingest"}
print("Real Airflow SDK parsed four tasks, dependencies, manual schedule and safe defaults.")
