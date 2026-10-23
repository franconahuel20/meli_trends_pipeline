"""The Dagster code location loads and wires the pipeline as expected."""

import pytest
from dagster import AssetKey, DefaultScheduleStatus, DefaultSensorStatus

from meli_trends_pipeline.automation import FINAL_ASSET_KEY, JOB_NAME
from meli_trends_pipeline.definitions import defs


@pytest.fixture(scope="module")
def asset_graph():
    return defs.resolve_asset_graph()


def key(path: str) -> AssetKey:
    return AssetKey(path.split("/"))


def test_asset_lineage(asset_graph):
    parents = {
        k.to_user_string(): {p.to_user_string() for p in asset_graph.get(k).parent_keys}
        for k in asset_graph.get_all_asset_keys()
    }
    assert parents == {
        "standardization_revenue_research_meli/brands": set(),
        "standardization_revenue_research_meli/characters": set(),
        "standardization_revenue_research_meli/mercado_libre_subcat": set(),
        "meli_datalake/trends_l1_raw": {"standardization_revenue_research_meli/mercado_libre_subcat"},
        "meli_datalake/trends_l2_clean": {"meli_datalake/trends_l1_raw"},
        "stg_revenue_research_meli/meli_trends_l3": {
            "meli_datalake/trends_l2_clean",
            "standardization_revenue_research_meli/brands",
            "standardization_revenue_research_meli/characters",
            "standardization_revenue_research_meli/mercado_libre_subcat",
        },
        "trends": {"stg_revenue_research_meli/meli_trends_l3"},
    }


def test_final_table_and_dbt_tests(asset_graph):
    final = asset_graph.get(FINAL_ASSET_KEY)
    assert final.group_name == "analytics"
    assert len(final.check_keys) >= 5  # dbt data tests surface as asset checks


def test_job_covers_every_asset(asset_graph):
    job = defs.resolve_job_def(JOB_NAME)
    assert len(job.graph.node_dict) == 7


def test_schedule_and_first_run_sensor():
    schedule = defs.resolve_schedule_def("meli_trends_daily_schedule")
    assert schedule.cron_schedule == "0 23 * * *"
    assert schedule.execution_timezone == "America/Argentina/Buenos_Aires"
    assert schedule.default_status == DefaultScheduleStatus.RUNNING

    sensor = defs.resolve_sensor_def("meli_trends_first_run_sensor")
    assert sensor.default_status == DefaultSensorStatus.RUNNING


def test_resources_are_bound():
    resources = defs.resources
    assert set(resources) == {"postgres", "minio", "mercadolibre", "dbt"}
