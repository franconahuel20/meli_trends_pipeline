"""Job, daily schedule and the first-start sensor of the pipeline."""

from datetime import datetime

from dagster import (
    AssetKey,
    AssetSelection,
    Backoff,
    DagsterRunStatus,
    DefaultScheduleStatus,
    DefaultSensorStatus,
    RetryPolicy,
    RunRequest,
    RunsFilter,
    ScheduleDefinition,
    SensorEvaluationContext,
    SkipReason,
    define_asset_job,
    sensor,
)

from .settings import MDM_SCHEMA, PipelineSettings

JOB_NAME = "meli_trends_pipeline_job"
# dbt model `trends` (schema mdm_revenue_research_meli): the table Superset reads.
FINAL_ASSET_KEY = AssetKey(["trends"])

_IN_FLIGHT = [
    DagsterRunStatus.QUEUED,
    DagsterRunStatus.NOT_STARTED,
    DagsterRunStatus.STARTING,
    DagsterRunStatus.STARTED,
]

settings = PipelineSettings.from_env()

meli_trends_pipeline_job = define_asset_job(
    name=JOB_NAME,
    selection=AssetSelection.all(),
    description=(
        "End to end: Excel reference tables -> Mercado Libre API (L1) -> clean (L2) -> "
        f"brand/character matching (L3) -> dbt model {MDM_SCHEMA}.trends."
    ),
    op_retry_policy=RetryPolicy(max_retries=2, delay=30, backoff=Backoff.EXPONENTIAL),
    tags={"pipeline": "meli_trends_pipeline"},
)

meli_trends_daily_schedule = ScheduleDefinition(
    name="meli_trends_daily_schedule",
    job=meli_trends_pipeline_job,
    cron_schedule=settings.schedule_cron,
    execution_timezone=settings.timezone,
    default_status=DefaultScheduleStatus.RUNNING,
    description=f"Runs the pipeline at '{settings.schedule_cron}' ({settings.timezone}).",
)


@sensor(
    name="meli_trends_first_run_sensor",
    job=meli_trends_pipeline_job,
    minimum_interval_seconds=60,
    default_status=(
        DefaultSensorStatus.RUNNING if settings.run_on_startup else DefaultSensorStatus.STOPPED
    ),
    description=(
        "Launches the pipeline right after `docker compose up` when the final table has never "
        "been built, so dashboards have data without waiting for the schedule. At most one "
        "attempt per day; afterwards the daily schedule takes over."
    ),
)
def meli_trends_first_run_sensor(context: SensorEvaluationContext):
    if context.instance.get_latest_materialization_event(FINAL_ASSET_KEY) is not None:
        return SkipReason("The final table has already been materialized.")
    in_flight = context.instance.get_runs(
        filters=RunsFilter(job_name=JOB_NAME, statuses=_IN_FLIGHT), limit=1
    )
    if in_flight:
        return SkipReason(f"Run {in_flight[0].run_id} is already in progress.")
    today = datetime.now(settings.tz).date().isoformat()
    return RunRequest(run_key=f"first-run-{today}", tags={"trigger": "first_run_sensor"})
