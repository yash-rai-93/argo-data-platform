"""Manual, single-host candidate workflow. Publication remains a reviewed GitHub operation."""

from datetime import timedelta

from airflow.sdk import Param, dag, get_current_context, task


@dag(
    dag_id="argo_community_incremental",
    schedule=None,
    catchup=False,
    max_active_runs=1,
    dagrun_timeout=timedelta(hours=2),
    default_args={"retries": 1, "retry_delay": timedelta(minutes=2)},
    tags=["argo", "community"],
    params={
        "apply": Param(False, type="boolean", description="Explicitly permit a capped data query."),
        "end_date": Param("", type="string", description="Exclusive UTC end; blank resolves once."),
        "maximum_bytes_billed": Param(0, type="integer", minimum=0, maximum=20000000000),
        "total_max_bytes_billed": Param(
            10000000000, type="integer", minimum=1, maximum=20000000000
        ),
    },
)
def community_refresh():
    @task
    def prepare_run():
        from orchestration.community_tasks import prepare

        context = get_current_context()
        return prepare(context["params"], context["run_id"])

    @task(execution_timeout=timedelta(minutes=30))
    def estimate(settings):
        from orchestration.community_tasks import execute

        return execute(settings, "estimate")

    @task(execution_timeout=timedelta(minutes=30))
    def ingest(settings, estimate_result):
        from orchestration.community_tasks import ingest as run_ingestion

        return run_ingestion(settings, estimate_result)

    @task(execution_timeout=timedelta(minutes=5))
    def validate_candidate(settings, ingestion_result):
        from orchestration.community_tasks import verify

        receipt = verify(settings, ingestion_result)
        print(receipt)
        return receipt

    settings = prepare_run()
    estimate_result = estimate(settings)
    ingestion_result = ingest(settings, estimate_result)
    validate_candidate(settings, ingestion_result)


community_dag = community_refresh()
