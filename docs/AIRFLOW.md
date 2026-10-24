# Airflow candidate orchestration

The manual argo_community_incremental DAG prepares a pinned run, estimates the
query, optionally ingests, and verifies its candidate. It reuses the existing
incremental controller and durable GCS query reservations. No Airflow server,
schedule, or always-on compute is deployed by this change.

## Runtime requirements

This first deployment supports **one host with LocalExecutor and shared local
storage**. Tasks must see the same immutable checkout and run directory.
Distributed workers and ephemeral task filesystems are not supported.

Install the project's locked Python 3.12 environment using uv sync --frozen.
Run Airflow separately; configure its supported metadata database before deployment.
Expose the checkout root on the Airflow process's PYTHONPATH and point its DAG
folder at the checkout's dags directory. CI parses the actual DAG with Airflow
3.3.2 in an isolated environment; Airflow is not added to dashboard/API dependencies.

Required runtime environment:

- ARGO_CHECKOUT_ROOT: absolute path to the immutable deployed checkout.
- ARGO_ETL_PYTHON: absolute path to that checkout's installed ETL Python.
- GOOGLE_CLOUD_PROJECT: explicit billing project.
- GCS_BUCKET: existing private US bucket's bare name.

Use Application Default Credentials from an attached runtime service account.
Existing GitHub WIF trust does **not** authenticate an Airflow VM. Choose and
verify runtime identity and bucket-scoped permissions during deployment; do not
broaden GitHub WIF trust or create service-account keys.

Do not update a checkout during a run. Preparation pins the commit, approved
pointer, UTC end and query caps. Changed inputs fail before querying.
Per-run local files live under data/generated/airflow/SHA256_OF_RUN_ID/.
Event files remain there and in private GCS; XCom contains settings, small reports
and verification receipts, not event rows or credentials.

## Manual validation sequence

1. Finish the first incremental GitHub Actions estimate/apply and report promotion.
2. Choose Airflow hosting size, region, runtime identity and spending allowance.
   Provisioning is separate from this code change.
3. Deploy paused with no schedule, no catchup and one active run. CI parsing does
   not prove a live scheduler. Tasks have bounded timeouts and one retry.
4. Trigger with apply=false, maximum_bytes_billed=0 and an exclusive UTC end_date.
   Blank end resolves once during preparation. Inspect the estimate.
5. Trigger a **new run** with that explicit end, apply=true, a query cap above
   the estimate and the same total cap. The existing GCS execution pins the total.
   Caps are at most 20,000,000,000 bytes, not universal rupee spending limits.
6. Inspect the final candidate_verified receipt and audit. A no-op or estimate-only
   run explicitly returns published=false; both are successful outcomes.
7. Publish using the existing main-only community-incremental-refresh GitHub
   workflow with the receipt's end and caps. It can reuse the completed GCS
   execution when predecessor, scope and query contract are unchanged.
   Review and merge the pointer PR after CI. Airflow holds no GitHub write token.
8. Verify production totals and Data Trust evidence. Exercise interrupted ingestion
   and retries; record actual runtime and costs before enabling a schedule.

A confirmed failed query requires the explicit recovery flow documented in
INCREMENTAL_COMMUNITY.md; this DAG does not automatically spend another reservation.
GCS generation preconditions also protect against concurrent manual Actions runs.
Airflow's one-active-run limit applies only to this DAG.

Publication remains reviewed. Do not claim automatic publication, live Airflow
deployment, scheduled ingestion, or streaming based on this DAG alone.
Kafka/PySpark and recovery/lag benchmarks remain later milestones.

Official references:

- https://airflow.apache.org/docs/task-sdk/stable/
- https://airflow.apache.org/docs/apache-airflow/stable/core-concepts/params.html
