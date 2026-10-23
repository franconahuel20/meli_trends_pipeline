import os
import sys
from pathlib import Path

import pandas as pd
import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DBT_DIR = PROJECT_ROOT / "dbt"

# Make the `dbt` executable of the running interpreter visible even when the
# virtualenv is not activated (DbtCliResource validates it at import time).
os.environ["PATH"] = str(Path(sys.executable).parent) + os.pathsep + os.environ.get("PATH", "")


def pytest_configure(config):
    """Build the dbt manifest when it is missing (the Docker image already ships one)."""
    if (DBT_DIR / "target" / "manifest.json").exists():
        return
    from dbt.cli.main import dbtRunner

    result = dbtRunner().invoke(
        ["parse", "--project-dir", str(DBT_DIR), "--profiles-dir", str(DBT_DIR / "profiles"), "--quiet"]
    )
    if not result.success:
        raise RuntimeError(f"dbt parse failed: {result.exception}")


@pytest.fixture(scope="session")
def reference_frames():
    """The real reference tables, read exactly as the pipeline loads them."""
    from meli_trends_pipeline.assets.reference_data import (
        BRANDS,
        CHARACTERS,
        SUBCATEGORIES,
        read_reference_excel,
    )

    input_dir = PROJECT_ROOT / "data" / "input"
    return {
        table.name: read_reference_excel(input_dir / table.file_name, table)
        for table in (BRANDS, CHARACTERS, SUBCATEGORIES)
    }


@pytest.fixture(scope="session")
def real_matcher(reference_frames):
    from meli_trends_pipeline.matching import build_matcher

    subcat = reference_frames["mercado_libre_subcat"]
    categories = pd.concat(
        [subcat["homologated_category_str"], subcat["homologated_subcategory_str"]]
    ).dropna()
    return build_matcher(reference_frames["brands"], reference_frames["characters"], categories)
