"""Pipeline settings and data-lake/warehouse names.

Everything tunable comes from environment variables (see ``.env.example``);
docker-compose passes them to the Dagster containers with safe defaults.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from zoneinfo import ZoneInfo

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DBT_PROJECT_DIR = PROJECT_ROOT / "dbt"

STANDARDIZATION_SCHEMA = "standardization_revenue_research_meli"
STAGING_SCHEMA = "stg_revenue_research_meli"
STAGING_TABLE = "meli_trends_l3"
MDM_SCHEMA = "mdm_revenue_research_meli"

L1_PREFIX = "L1_delta/revenue_research_meli/trends"
L2_PREFIX = "L2_databases/revenue_research_meli/trends"
L3_PREFIX = "L3_standardization/revenue_research_meli/trends"

_TRUE = {"1", "true", "yes", "y", "on"}
_FALSE = {"0", "false", "no", "n", "off"}


def env_str(name: str, default: str) -> str:
    value = os.getenv(name, "").strip()
    return value or default


def env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name, "").strip().lower()
    if not value:
        return default
    if value in _TRUE:
        return True
    if value in _FALSE:
        return False
    raise ValueError(f"{name} must be true or false, got {value!r}")


def env_int(name: str, default: int, minimum: int = 1) -> int:
    value = os.getenv(name, "").strip()
    if not value:
        return default
    try:
        number = int(value)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer, got {value!r}") from exc
    if number < minimum:
        raise ValueError(f"{name} must be >= {minimum}, got {number}")
    return number


@dataclass(frozen=True)
class PipelineSettings:
    timezone: str
    schedule_cron: str
    run_on_startup: bool
    input_dir: Path
    selected_subcategories_only: bool
    meli_max_workers: int
    fuzzy_matching_enabled: bool

    @property
    def tz(self) -> ZoneInfo:
        return ZoneInfo(self.timezone)

    @classmethod
    def from_env(cls) -> "PipelineSettings":
        settings = cls(
            timezone=env_str("PIPELINE_TIMEZONE", "America/Argentina/Buenos_Aires"),
            schedule_cron=env_str("PIPELINE_SCHEDULE_CRON", "0 23 * * *"),
            run_on_startup=env_bool("PIPELINE_RUN_ON_STARTUP", True),
            input_dir=Path(env_str("PIPELINE_INPUT_DIR", str(PROJECT_ROOT / "data" / "input"))),
            selected_subcategories_only=env_bool("MELI_SELECTED_SUBCATEGORIES_ONLY", True),
            meli_max_workers=env_int("MELI_MAX_WORKERS", 4),
            fuzzy_matching_enabled=env_bool("MATCHING_FUZZY_ENABLED", True),
        )
        settings.tz  # fail fast on an unknown time zone name
        return settings
