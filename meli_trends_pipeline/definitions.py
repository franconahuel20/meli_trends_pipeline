"""Dagster code location: `dagster api grpc -m meli_trends_pipeline.definitions`."""

from __future__ import annotations

from dagster import Definitions, EnvVar
from dagster_dbt import DbtCliResource

from .assets import (
    dbt_project,
    meli_trends_dbt_models,
    meli_trends_l3,
    reference_assets,
    trends_l1_raw,
    trends_l2_clean,
)
from .automation import meli_trends_daily_schedule, meli_trends_first_run_sensor, meli_trends_pipeline_job
from .resources import MercadoLibreResource, MinioResource, PostgresResource
from .settings import env_int, env_str

defs = Definitions(
    assets=[*reference_assets, trends_l1_raw, trends_l2_clean, meli_trends_l3, meli_trends_dbt_models],
    jobs=[meli_trends_pipeline_job],
    schedules=[meli_trends_daily_schedule],
    sensors=[meli_trends_first_run_sensor],
    resources={
        # Secrets go through EnvVar so the Dagster UI shows the variable name, not the value.
        "postgres": PostgresResource(
            host=env_str("POSTGRES_HOST", "postgres"),
            port=env_int("POSTGRES_PORT", 5432),
            database=env_str("POSTGRES_DB", "snowflake_dev"),
            user=env_str("POSTGRES_USER", "postgres"),
            password=EnvVar("POSTGRES_PASSWORD"),
        ),
        "minio": MinioResource(
            endpoint_url=env_str("MINIO_ENDPOINT", "http://minio:9000"),
            access_key=EnvVar("MINIO_ROOT_USER"),
            secret_key=EnvVar("MINIO_ROOT_PASSWORD"),
            bucket=env_str("MINIO_BUCKET", "meli-datalake"),
        ),
        "mercadolibre": MercadoLibreResource(
            client_id=EnvVar("ML_CLIENT_ID"),
            client_secret=EnvVar("ML_CLIENT_SECRET"),
            grant_type=env_str("ML_GRANT_TYPE", "client_credentials"),
        ),
        "dbt": DbtCliResource(project_dir=dbt_project),
    },
)
