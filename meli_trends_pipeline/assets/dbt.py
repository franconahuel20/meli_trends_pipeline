"""dbt models exposed as Dagster assets (one asset per model, tests as asset checks)."""

import json
from pathlib import Path

from dagster import AssetExecutionContext
from dagster_dbt import DbtCliResource, DbtProject, dbt_assets

from ..resources import PostgresResource
from ..settings import DBT_PROJECT_DIR, MDM_SCHEMA
from ..warehouse import table_columns

FINAL_MODEL = "model.meli_trends_pipeline.trends"
FINAL_TABLE = "trends"

dbt_project = DbtProject(project_dir=DBT_PROJECT_DIR, profiles_dir=DBT_PROJECT_DIR / "profiles")
# Parses the project when running `dagster dev`; the Docker image ships a manifest built at build time.
dbt_project.prepare_if_dev()


def documented_columns(manifest_path: Path) -> list[str]:
    """Columns of the final model in the order schema.yml lists them (the table order)."""
    manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    return list(manifest["nodes"][FINAL_MODEL]["columns"])


@dbt_assets(manifest=dbt_project.manifest_path, project=dbt_project)
def meli_trends_dbt_models(
    context: AssetExecutionContext, dbt: DbtCliResource, postgres: PostgresResource
):
    args = ["build"]
    # An incremental model only appends new columns; when the layout of the final table
    # changed (columns added, removed or reordered) rebuild it from the staging history.
    with postgres.connection() as conn, conn.cursor() as cur:
        existing = table_columns(cur, MDM_SCHEMA, FINAL_TABLE)
    expected = documented_columns(dbt_project.manifest_path)
    if existing and existing != expected:
        context.log.warning(
            "%s.%s has a different layout than the dbt model; running a full refresh.",
            MDM_SCHEMA,
            FINAL_TABLE,
        )
        args.append("--full-refresh")
    yield from dbt.cli(args, context=context).stream()
