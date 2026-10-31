"""Trend extraction (L1), cleaning (L2) and brand/character standardization (L3)."""

import csv
import io
import posixpath
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime

import pandas as pd
from dagster import (
    AssetExecutionContext,
    AssetIn,
    AssetKey,
    Config,
    Failure,
    MaterializeResult,
    MetadataValue,
    Output,
    asset,
)
from psycopg2 import sql
from pydantic import Field

from ..matching import L3_COLUMNS, MatchingConfig, build_matcher, enrich_trends
from ..matching.enrichment import SOURCE_FILE_COLUMN, SOURCE_ROW_COLUMN
from ..matching.linguistics import SpacyAnalyzer
from ..resources import MercadoLibreResource, MinioResource, PostgresResource
from ..settings import (
    L1_PREFIX,
    L2_PREFIX,
    L3_PREFIX,
    STAGING_SCHEMA,
    STAGING_TABLE,
    STANDARDIZATION_SCHEMA,
    PipelineSettings,
)
from ..warehouse import Column, copy_dataframe, ensure_table, qualified, read_dataframe
from .metadata import markdown_table
from .reference_data import BRANDS, CHARACTERS, SUBCATEGORIES

L1_KEY = AssetKey(["meli_datalake", "trends_l1_raw"])
L2_KEY = AssetKey(["meli_datalake", "trends_l2_clean"])
L3_KEY = AssetKey([STAGING_SCHEMA, STAGING_TABLE])

L1_COLUMNS = ["Keyword", "URL", "Date", "Country", "Category", "Subcategory"]
L2_RENAME = {
    "Keyword": "keyword_str",
    "URL": "url_str",
    "Date": "date_dte",
    "Country": "country_str",
    "Category": "category_str",
    "Subcategory": "subcategory_str",
}
_SUBCATEGORY_CODE = re.compile(r"^M[A-Z]{2}\d+$")
_PARTITION = re.compile(r"/date_dte=(\d{4}-\d{2}-\d{2})/meli_trends\.parquet$")
# A run with more failed API calls than this is retried instead of publishing partial data.
MAX_FAILED_CALL_RATIO = 0.5

_INTEGER_COLUMNS = {
    "brand_match_score_int",
    "character_match_score_int",
    "twdc_int",
    "year_calendar_int",
    "month_calendar_int",
    "day_calendar_int",
    "file_row_id_int",
}
_NOT_NULL_COLUMNS = {"keyword_str", "date_dte", "country_str", "branded_str"}


def _staging_column(name: str) -> Column:
    if name in _INTEGER_COLUMNS:
        sql_type = "INTEGER"
    elif name == "date_dte":
        sql_type = "DATE"
    elif name == "loading_dtm":
        sql_type = "TIMESTAMPTZ"
    else:
        sql_type = "TEXT"
    return Column(name, sql_type, nullable=name not in _NOT_NULL_COLUMNS)


STAGING_COLUMNS = tuple(_staging_column(name) for name in L3_COLUMNS)


def _parquet_bytes(df: pd.DataFrame) -> bytes:
    buffer = io.BytesIO()
    df.to_parquet(buffer, index=False, engine="pyarrow")
    return buffer.getvalue()


def _partition_key(prefix: str, snapshot_date: str) -> str:
    return f"{prefix}/date_dte={snapshot_date}/meli_trends.parquet"


def _l1_key(snapshot_date: date) -> str:
    return f"{L1_PREFIX}/mercado_libre_trends_{snapshot_date:%d%m%Y}.csv"


def _l2_partitions(minio: MinioResource) -> dict[str, str]:
    """Snapshot date -> L2 parquet key, for every day kept in the data lake."""
    partitions = {}
    for key in minio.list_keys(f"{L2_PREFIX}/"):
        found = _PARTITION.search(key)
        if found:
            partitions[found.group(1)] = key
    return partitions


def _read_subcategories(postgres: PostgresResource, selected_only: bool) -> pd.DataFrame:
    query = sql.SQL(
        """
        SELECT cod_subcat_str,
               country_str,
               COALESCE(homologated_category_str, category_api_str) AS category_str,
               COALESCE(homologated_subcategory_str, subcategory_str) AS subcategory_str
        FROM {table}
        WHERE cod_subcat_str IS NOT NULL {selected}
        ORDER BY country_str, cod_subcat_str
        """
    ).format(
        table=qualified(STANDARDIZATION_SCHEMA, SUBCATEGORIES.name),
        selected=sql.SQL("AND id_selected_int = 1") if selected_only else sql.SQL(""),
    )
    with postgres.connection() as conn:
        df = read_dataframe(conn, query)
    return df.drop_duplicates("cod_subcat_str").reset_index(drop=True)


@asset(
    key=L1_KEY,
    deps=[SUBCATEGORIES.asset_key],
    group_name="trends",
    kinds={"python", "s3"},
    description=(
        "Calls GET /trends/{site}/{category} for every selected subcategory and stores the "
        "raw CSV in MinIO: L1_delta/.../mercado_libre_trends_ddmmyyyy.csv."
    ),
)
def trends_l1_raw(
    context: AssetExecutionContext,
    postgres: PostgresResource,
    minio: MinioResource,
    mercadolibre: MercadoLibreResource,
) -> Output[dict]:
    settings = PipelineSettings.from_env()
    snapshot = datetime.now(settings.tz)
    subcategories = _read_subcategories(postgres, settings.selected_subcategories_only)
    valid = subcategories["cod_subcat_str"].str.strip().str.upper().str.match(_SUBCATEGORY_CODE)
    if (~valid).any():
        context.log.warning(
            "Skipping %s invalid subcategory codes: %s",
            int((~valid).sum()),
            subcategories.loc[~valid, "cod_subcat_str"].tolist()[:20],
        )
    subcategories = subcategories[valid]
    if subcategories.empty:
        raise Failure(description="No subcategories to extract; check mercado_libre_subcat.xlsx.")

    client = mercadolibre.create_client()
    client.access_token()  # fail fast on bad credentials before fanning out

    def fetch(row: dict):
        code = row["cod_subcat_str"].strip().upper()
        return row, client.trends(code[:3], code)

    rows: list[dict] = []
    failures: list[str] = []
    empty = 0
    with ThreadPoolExecutor(max_workers=settings.meli_max_workers) as pool:
        for row, response in pool.map(fetch, subcategories.to_dict("records")):
            if response.error:
                failures.append(f"{row['cod_subcat_str']}: HTTP {response.status_code} {response.error}")
                continue
            if not response.items:
                empty += 1
                continue
            for item in response.items:
                rows.append(
                    {
                        "Keyword": item.get("keyword"),
                        "URL": item.get("url"),
                        "Date": snapshot.date().isoformat(),
                        "Country": row["country_str"],
                        "Category": row["category_str"],
                        "Subcategory": row["subcategory_str"],
                    }
                )

    calls = len(subcategories)
    context.log.info(
        "API calls: %s | with trends: %s | empty: %s | failed: %s | rows: %s",
        calls, calls - empty - len(failures), empty, len(failures), len(rows),
    )
    for failure in failures[:20]:
        context.log.warning(failure)
    if not rows or len(failures) > MAX_FAILED_CALL_RATIO * calls:
        raise Failure(
            description=(
                f"Mercado Libre extraction failed: {len(failures)} of {calls} calls failed, "
                f"{len(rows)} rows retrieved."
            ),
            metadata={"sample_errors": MetadataValue.text("\n".join(failures[:20]))},
        )

    df = pd.DataFrame(rows, columns=L1_COLUMNS)
    key = _l1_key(snapshot.date())
    body = df.to_csv(sep=";", index=False, quoting=csv.QUOTE_MINIMAL).encode("utf-8")
    uri = minio.put_bytes(key, body, "text/csv; charset=utf-8")
    return Output(
        {"snapshot_date": snapshot.date().isoformat(), "key": key},
        metadata={
            "uri": MetadataValue.text(uri),
            "rows": MetadataValue.int(len(df)),
            "api_calls": MetadataValue.int(calls),
            "failed_calls": MetadataValue.int(len(failures)),
            "empty_calls": MetadataValue.int(empty),
        },
    )


@asset(
    key=L2_KEY,
    ins={"l1": AssetIn(L1_KEY)},
    group_name="trends",
    kinds={"python", "s3", "parquet"},
    description="Trims, drops empty keywords and duplicates; writes parquet to L2 partitioned by date.",
)
def trends_l2_clean(context: AssetExecutionContext, l1: dict, minio: MinioResource) -> Output[dict]:
    raw = pd.read_csv(
        io.BytesIO(minio.get_bytes(l1["key"])),
        sep=";",
        dtype=str,
        keep_default_na=False,
        encoding="utf-8",
    )
    missing = [c for c in L1_COLUMNS if c not in raw.columns]
    if missing:
        raise Failure(description=f"L1 file {l1['key']} is missing columns {missing}")

    df = raw.loc[:, L1_COLUMNS].rename(columns=L2_RENAME)
    for column in df.columns:
        df[column] = df[column].map(lambda v: " ".join(str(v).split()) or None)
    # Lineage to the raw file: its name and the 0-based row number inside it.
    df[SOURCE_FILE_COLUMN] = posixpath.basename(l1["key"])
    df[SOURCE_ROW_COLUMN] = range(len(df))
    df = df[df["keyword_str"].notna()].copy()
    df["date_dte"] = pd.to_datetime(df["date_dte"], errors="raise").dt.date
    before = len(df)
    df = df.drop_duplicates(subset=list(L2_RENAME.values())).reset_index(drop=True)

    key = _partition_key(L2_PREFIX, l1["snapshot_date"])
    uri = minio.put_bytes(key, _parquet_bytes(df), "application/vnd.apache.parquet")
    context.log.info("L2: %s rows (%s raw, %s duplicates removed)", len(df), len(raw), before - len(df))
    return Output(
        {"snapshot_date": l1["snapshot_date"], "key": key},
        metadata={
            "uri": MetadataValue.text(uri),
            "rows": MetadataValue.int(len(df)),
            "dropped_rows": MetadataValue.int(len(raw) - len(df)),
        },
    )


def _method_counts(series: pd.Series) -> dict[str, int]:
    return {str(k): int(v) for k, v in series.value_counts(dropna=True).items()}


class TrendsL3Config(Config):
    reprocess_history: bool = Field(
        default=False,
        description=(
            "Re-match every snapshot date kept in L2, not only today's. Use it after changing "
            "the reference files or the matching word lists; dbt then refreshes those dates."
        ),
    )


@asset(
    key=L3_KEY,
    ins={"l2": AssetIn(L2_KEY)},
    deps=[BRANDS.asset_key, CHARACTERS.asset_key, SUBCATEGORIES.asset_key],
    group_name="trends",
    kinds={"python", "postgres", "s3"},
    description=(
        "Matches each keyword against brands and characters (precision-first rules), adds "
        "franchise attributes, lemmas and flags, writes L3 parquet and upserts the snapshot date "
        "into stg_revenue_research_meli.meli_trends_l3. Dates kept in L2 but missing from the "
        "staging table (for example after a layout change) are rebuilt in the same run."
    ),
)
def meli_trends_l3(
    context: AssetExecutionContext,
    config: TrendsL3Config,
    l2: dict,
    postgres: PostgresResource,
    minio: MinioResource,
) -> MaterializeResult:
    settings = PipelineSettings.from_env()

    with postgres.connection() as conn:
        brands = read_dataframe(
            conn,
            sql.SQL("SELECT brand_str, branded_int FROM {}").format(
                qualified(STANDARDIZATION_SCHEMA, BRANDS.name)
            ),
        )
        characters = read_dataframe(
            conn,
            sql.SQL("SELECT * FROM {} ORDER BY number_id_int NULLS LAST").format(
                qualified(STANDARDIZATION_SCHEMA, CHARACTERS.name)
            ),
        )
        categories = read_dataframe(
            conn,
            sql.SQL(
                "SELECT DISTINCT homologated_category_str, homologated_subcategory_str FROM {}"
            ).format(qualified(STANDARDIZATION_SCHEMA, SUBCATEGORIES.name)),
        )

    category_terms = pd.concat(
        [categories["homologated_category_str"], categories["homologated_subcategory_str"]]
    ).dropna()
    matcher = build_matcher(
        brands,
        characters,
        category_terms,
        config=MatchingConfig(fuzzy_enabled=settings.fuzzy_matching_enabled),
    )
    analyzer = SpacyAnalyzer()

    target = qualified(STAGING_SCHEMA, STAGING_TABLE)
    with postgres.connection() as conn:
        with conn.cursor() as cur:
            backup = ensure_table(cur, STAGING_SCHEMA, STAGING_TABLE, STAGING_COLUMNS)
            if backup:
                context.log.warning(
                    "Staging table had an old layout; kept it as %s.%s and rebuilding every "
                    "date from L2.", STAGING_SCHEMA, backup,
                )
            cur.execute(
                sql.SQL("CREATE INDEX IF NOT EXISTS {} ON {} (date_dte)").format(
                    sql.Identifier(f"ix_{STAGING_TABLE}_date_dte"), target
                )
            )
            cur.execute(sql.SQL("SELECT DISTINCT date_dte FROM {}").format(target))
            loaded = {row[0].isoformat() for row in cur.fetchall()}
        conn.commit()

    snapshot_date = l2["snapshot_date"]
    partitions = {**_l2_partitions(minio), snapshot_date: l2["key"]}
    dates = sorted(
        d for d in partitions if config.reprocess_history or d == snapshot_date or d not in loaded
    )
    context.log.info("Matching %s snapshot date(s): %s", len(dates), ", ".join(dates))

    snapshot_l3 = None
    for day in dates:
        trends = pd.read_parquet(io.BytesIO(minio.get_bytes(partitions[day])))
        if SOURCE_FILE_COLUMN not in trends:  # partitions written before lineage was kept
            trends[SOURCE_FILE_COLUMN] = posixpath.basename(_l1_key(date.fromisoformat(day)))
        l3 = enrich_trends(trends, matcher, datetime.now(settings.tz), analyzer)
        minio.put_bytes(
            _partition_key(L3_PREFIX, day), _parquet_bytes(l3), "application/vnd.apache.parquet"
        )
        with postgres.connection() as conn:
            with conn.cursor() as cur:
                # Idempotent per snapshot date: a re-run replaces that day only.
                cur.execute(sql.SQL("DELETE FROM {} WHERE date_dte = %s").format(target), (day,))
                copy_dataframe(cur, STAGING_SCHEMA, STAGING_TABLE, l3)
            conn.commit()
        branded = int((l3["branded_str"] == "Branded").sum())
        context.log.info(
            "L3 %s: %s rows, %s with brand, %s branded (%.1f%%)",
            day, len(l3), int(l3["brand_str"].notna().sum()), branded, 100 * branded / max(len(l3), 1),
        )
        if day == snapshot_date:
            snapshot_l3 = l3

    l3 = snapshot_l3
    branded = int((l3["branded_str"] == "Branded").sum())
    top = (
        l3.loc[l3["branded_str"] == "Branded", ["keyword_str", "brand_str", "character_str"]]
        .value_counts(dropna=False)
        .reset_index(name="rows")
    )
    return MaterializeResult(
        metadata={
            "uri": MetadataValue.text(f"s3://{minio.bucket}/{_partition_key(L3_PREFIX, snapshot_date)}"),
            "rows": MetadataValue.int(len(l3)),
            "snapshot_date": MetadataValue.text(snapshot_date),
            "processed_dates": MetadataValue.text(", ".join(dates)),
            "rows_with_brand": MetadataValue.int(int(l3["brand_str"].notna().sum())),
            "branded_rows": MetadataValue.int(branded),
            "branded_share": MetadataValue.float(round(branded / max(len(l3), 1), 4)),
            "brand_matches_by_method": MetadataValue.json(_method_counts(l3["brand_match_method_str"])),
            "character_matches_by_method": MetadataValue.json(
                _method_counts(l3["character_match_method_str"])
            ),
            "top_brands": MetadataValue.json(
                {str(k): int(v) for k, v in l3["brand_str"].value_counts().head(20).items()}
            ),
            "top_branded_keywords": MetadataValue.md(markdown_table(top, max_rows=20)),
        }
    )
