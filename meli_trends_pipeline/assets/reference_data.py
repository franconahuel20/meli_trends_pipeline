"""Reference tables loaded from the Excel files in ``data/input``."""

from dataclasses import dataclass

import pandas as pd
from dagster import AssetExecutionContext, AssetKey, AssetsDefinition, MaterializeResult, MetadataValue, asset
from psycopg2 import sql

from ..matching.text import is_missing, normalize_text
from ..resources import PostgresResource
from ..settings import STANDARDIZATION_SCHEMA, PipelineSettings
from ..warehouse import Column, copy_dataframe, create_table, qualified
from .metadata import markdown_table


@dataclass(frozen=True)
class SourceColumn:
    header: str  # normalized Excel header
    column: Column


@dataclass(frozen=True)
class ReferenceTable:
    name: str
    file_name: str
    key_column: str
    columns: tuple[SourceColumn, ...]
    indexes: tuple[tuple[str, ...], ...] = ()
    description: str = ""

    @property
    def asset_key(self) -> AssetKey:
        return AssetKey([STANDARDIZATION_SCHEMA, self.name])


BRANDS = ReferenceTable(
    name="brands",
    file_name="brands.xlsx",
    key_column="brand_str",
    columns=(
        SourceColumn("marca", Column("brand_str", "TEXT", nullable=False)),
        SourceColumn("branded", Column("branded_int", "INTEGER")),
    ),
    description="Brand master list used to detect branded searches.",
)

CHARACTERS = ReferenceTable(
    name="characters",
    file_name="characters.xlsx",
    key_column="character_str",
    columns=(
        SourceColumn("n", Column("number_id_int", "INTEGER")),
        SourceColumn("grupo empresa owner derechos", Column("group_company_owner_rights_str", "TEXT")),
        SourceColumn("twdc", Column("twdc_int", "INTEGER")),
        SourceColumn("franquicia n1", Column("franchise_n1_str", "TEXT")),
        SourceColumn("franquicia n2", Column("franchise_n2_str", "TEXT")),
        SourceColumn("franquicia n3", Column("franchise_n3_str", "TEXT")),
        SourceColumn("contenido", Column("content_str", "TEXT")),
        SourceColumn("personaje", Column("character_str", "TEXT", nullable=False)),
        SourceColumn("detalle", Column("detail_str", "TEXT")),
        SourceColumn("comentarios", Column("comment_str", "TEXT")),
    ),
    description="Characters with owner and franchise hierarchy (N1 > N2 > N3 > content).",
)

SUBCATEGORIES = ReferenceTable(
    name="mercado_libre_subcat",
    file_name="mercado_libre_subcat.xlsx",
    key_column="cod_subcat_str",
    columns=(
        SourceColumn("cod cat", Column("cat_code_str", "TEXT")),
        SourceColumn("categoria api", Column("category_api_str", "TEXT")),
        SourceColumn("cod subcat", Column("cod_subcat_str", "TEXT", nullable=False)),
        SourceColumn("subcategoria", Column("subcategory_str", "TEXT")),
        SourceColumn("items", Column("items_int", "INTEGER")),
        SourceColumn("pais", Column("country_str", "TEXT")),
        SourceColumn("categoria homologada", Column("homologated_category_str", "TEXT")),
        SourceColumn("id seleccionado", Column("id_selected_int", "INTEGER")),
        SourceColumn("subcategoria homologada", Column("homologated_subcategory_str", "TEXT")),
    ),
    indexes=(("id_selected_int", "cod_subcat_str"),),
    description="Mercado Libre subcategories per country; id_selected_int = 1 marks the ones to extract.",
)

REFERENCE_TABLES = (BRANDS, CHARACTERS, SUBCATEGORIES)


def _clean_text(value: object) -> str | None:
    if is_missing(value):
        return None
    text = " ".join(str(value).replace("\xa0", " ").split())
    return text or None


def read_reference_excel(path, table: ReferenceTable) -> pd.DataFrame:
    """Read an Excel file, map its (normalized) headers and coerce column types."""
    raw = pd.read_excel(path, dtype=object)
    raw.columns = [normalize_text(c) for c in raw.columns]
    missing = [c.header for c in table.columns if c.header not in raw.columns]
    if missing:
        raise ValueError(
            f"{table.file_name} is missing columns {missing}; found {list(raw.columns)}"
        )
    df = pd.DataFrame(index=raw.index)
    for source in table.columns:
        values = raw[source.header]
        if source.column.sql_type == "INTEGER":
            df[source.column.name] = pd.to_numeric(values, errors="coerce").round().astype("Int64")
        else:
            df[source.column.name] = values.map(_clean_text).astype(object)
    df = df[df[table.key_column].notna()].reset_index(drop=True)
    if df.empty:
        raise ValueError(f"{table.file_name} has no rows with a value in {table.key_column}")
    return df


def _reference_asset(table: ReferenceTable) -> AssetsDefinition:
    @asset(
        key=table.asset_key,
        group_name="reference_data",
        kinds={"excel", "postgres"},
        description=f"{table.description} Source: data/input/{table.file_name}.",
    )
    def _load(context: AssetExecutionContext, postgres: PostgresResource) -> MaterializeResult:
        settings = PipelineSettings.from_env()
        df = read_reference_excel(settings.input_dir / table.file_name, table)
        columns = [s.column for s in table.columns]
        target = qualified(STANDARDIZATION_SCHEMA, table.name)
        with postgres.connection() as conn:
            with conn.cursor() as cur:
                # Single transaction: the table is never seen empty or half loaded.
                cur.execute(sql.SQL("DROP TABLE IF EXISTS {}").format(target))
                create_table(cur, STANDARDIZATION_SCHEMA, table.name, columns)
                copy_dataframe(cur, STANDARDIZATION_SCHEMA, table.name, df)
                for index_columns in table.indexes:
                    cur.execute(
                        sql.SQL("CREATE INDEX ON {} ({})").format(
                            target, sql.SQL(", ").join(sql.Identifier(c) for c in index_columns)
                        )
                    )
            conn.commit()
        context.log.info("Loaded %s rows into %s.%s", len(df), STANDARDIZATION_SCHEMA, table.name)
        return MaterializeResult(
            metadata={
                "rows": MetadataValue.int(len(df)),
                "table": MetadataValue.text(f"{STANDARDIZATION_SCHEMA}.{table.name}"),
                "preview": MetadataValue.md(markdown_table(df)),
            }
        )

    return _load


reference_assets = [_reference_asset(table) for table in REFERENCE_TABLES]
