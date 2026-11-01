"""Generates the Superset import bundle of the "Revenue Research - Mercado Libre Trends" dashboard.

The dashboard reproduces the Revenue Research report (tabs Read Me, Summary, Market Landscape,
Franchise, Categories, Subcategories, Products and Trends) on the dbt table
mdm_revenue_research_meli.trends. Superset imports the bundle at start-up
(docker/superset/provision.py), so the dashboard is recreated even on a brand-new volume.

Edit this file, not the YAML, and regenerate:

    python superset/build_dashboard.py

Only PyYAML is required. UUIDs are derived from names, so regenerating is stable.
"""

from __future__ import annotations

import hashlib
import re
import shutil
import uuid
from pathlib import Path

import yaml

OUT_DIR = Path(__file__).resolve().parent / "dashboard"
NAMESPACE = uuid.UUID("6f1d0a52-5c3e-4b8e-9a51-7c2f3d8e1b40")
VERSION = "1.0.0"

DATABASE_NAME = "MeLi Trends (PostgreSQL)"
DATABASE_URI = "postgresql+psycopg2://postgres:XXXXXXXXXX@postgres:5432/snowflake_dev"
SCHEMA = "mdm_revenue_research_meli"
TABLE = "trends"
DASHBOARD_TITLE = "Revenue Research - Mercado Libre Trends"
DASHBOARD_SLUG = "meli-trends"
SOURCE_NOTE = "Fuente: Revenue Research - API Tendencias de Mercado Libre - Arg/Bra/Chi/Col/Méx"


def uid(*parts: str) -> str:
    return str(uuid.uuid5(NAMESPACE, "/".join(parts)))


def short_id(*parts: str) -> str:
    return hashlib.sha1("/".join(parts).encode()).hexdigest()[:10]


DATABASE_UUID = uid("database", DATABASE_NAME)
DATASET_UUID = uid("dataset", SCHEMA, TABLE)
DASHBOARD_UUID = uid("dashboard", DASHBOARD_SLUG)

# --------------------------------------------------------------------------------------
# Dataset: the final table plus two calculated columns used by the report.
# --------------------------------------------------------------------------------------

COLUMNS = [
    # name, type, verbose name
    ("keyword_str", "VARCHAR(1000)", "Keyword"),
    ("url_str", "VARCHAR(3000)", "URL"),
    ("date_dte", "DATE", "Fecha"),
    ("country_str", "VARCHAR(200)", "País"),
    ("category_str", "VARCHAR(200)", "Categoría"),
    ("subcategory_str", "VARCHAR(200)", "Subcategoría"),
    ("_internal_filename_str", "VARCHAR(300)", "Archivo de origen"),
    ("loading_dtm", "TIMESTAMP WITH TIME ZONE", "Fecha de carga"),
    ("file_row_id_int", "INTEGER", "Fila en archivo"),
    ("brand_str", "VARCHAR(200)", "Marca"),
    ("character_str", "VARCHAR(200)", "Personaje"),
    ("second_brand_str", "VARCHAR(200)", "Segunda marca"),
    ("group_company_owner_rights_str", "VARCHAR(500)", "Grupo Empresa Owner Derechos"),
    ("twdc_int", "INTEGER", "TWDC"),
    ("franchise_n1_str", "VARCHAR(200)", "Franquicia Nivel 1"),
    ("franchise_n2_str", "VARCHAR(200)", "Franquicia Nivel 2"),
    ("franchise_n3_str", "VARCHAR(200)", "Franquicia Nivel 3"),
    ("content_str", "VARCHAR(300)", "Contenido"),
    ("keyword_in_spanish_str", "VARCHAR(1000)", "Keyword (español)"),
    ("week_dte", "DATE", "Semana"),
    ("normalized_keyword_es_str", "VARCHAR(1000)", "Keyword normalizada"),
    ("keyword_es_without_stopwords_str", "VARCHAR(1000)", "Keyword sin stopwords"),
    ("character_without_stopwords_str", "VARCHAR(200)", "Personaje sin stopwords"),
    ("lemmatized_keyword_str", "VARCHAR(1000)", "Lemmatized"),
    ("nouns_keyword_str", "VARCHAR(1000)", "Sustantivos"),
    ("has_franchise_n2_str", "VARCHAR(5)", "Tiene franquicia N2"),
    ("has_franchise_n3_str", "VARCHAR(5)", "Tiene franquicia N3"),
    ("has_character_str", "VARCHAR(5)", "Tiene personaje"),
    ("has_franchise_n1_str", "VARCHAR(5)", "Tiene franquicia N1"),
    ("has_brand_str", "VARCHAR(5)", "Tiene marca"),
    ("branded_str", "VARCHAR(20)", "Branded"),
    ("year_calendar_int", "INTEGER", "Año"),
    ("month_calendar_int", "INTEGER", "Mes"),
    ("day_calendar_int", "INTEGER", "Día"),
]
CALCULATED_COLUMNS = [
    # The product of a search is its first noun: "camiseta neon fiesta" -> "camiseta".
    ("producto_str", "VARCHAR", "Producto", "NULLIF(split_part(nouns_keyword_str, ' ', 1), '')"),
    (
        "franquicia_si_no_str",
        "VARCHAR",
        "Franquicia",
        "CASE WHEN has_franchise_n1_str = 'YES' THEN 'SI' ELSE 'NO' END",
    ),
]
METRIC = "count"


def dataset_config() -> dict:
    columns = [
        {
            "column_name": name,
            "verbose_name": verbose,
            "is_dttm": sql_type in ("DATE", "TIMESTAMP WITH TIME ZONE"),
            "is_active": True,
            "type": sql_type,
            "advanced_data_type": None,
            "groupby": True,
            "filterable": True,
            "expression": None,
            "description": None,
            "python_date_format": None,
            "extra": {},
        }
        for name, sql_type, verbose in COLUMNS
    ]
    columns += [
        {
            "column_name": name,
            "verbose_name": verbose,
            "is_dttm": False,
            "is_active": True,
            "type": sql_type,
            "advanced_data_type": None,
            "groupby": True,
            "filterable": True,
            "expression": expression,
            "description": None,
            "python_date_format": None,
            "extra": {},
        }
        for name, sql_type, verbose, expression in CALCULATED_COLUMNS
    ]
    return {
        "table_name": TABLE,
        "main_dttm_col": "date_dte",
        "description": "Tendencias de Mercado Libre enriquecidas (tabla final de dbt).",
        "default_endpoint": None,
        "offset": 0,
        "cache_timeout": None,
        "schema": SCHEMA,
        "sql": None,
        "params": None,
        "template_params": None,
        "filter_select_enabled": True,
        "fetch_values_predicate": None,
        "extra": None,
        "normalize_columns": False,
        "always_filter_main_dttm": False,
        "uuid": DATASET_UUID,
        "metrics": [
            {
                "metric_name": METRIC,
                "verbose_name": "Búsquedas",
                "metric_type": "count",
                "expression": "COUNT(*)",
                "description": "Apariciones de keywords en las tendencias (keyword x subcategoría x día).",
                "d3format": ",d",
                "currency": None,
                "extra": {},
                "warning_text": None,
            }
        ],
        "columns": columns,
        "version": VERSION,
        "database_uuid": DATABASE_UUID,
    }


def database_config() -> dict:
    return {
        "database_name": DATABASE_NAME,
        "sqlalchemy_uri": DATABASE_URI,
        "cache_timeout": None,
        "expose_in_sqllab": True,
        "allow_run_async": False,
        "allow_ctas": False,
        "allow_cvas": False,
        "allow_dml": False,
        "allow_file_upload": False,
        "extra": {"allows_virtual_table_explore": True},
        "uuid": DATABASE_UUID,
        "version": VERSION,
    }


# --------------------------------------------------------------------------------------
# Chart building blocks (form data of Superset 4.1 ECharts / table / word cloud charts).
# --------------------------------------------------------------------------------------


def _filter(subject: str, operator: str, comparator=None) -> dict:
    return {
        "clause": "WHERE",
        "subject": subject,
        "operator": operator,
        "comparator": comparator,
        "expressionType": "SIMPLE",
        "isExtra": False,
        "isNew": False,
        "sqlExpression": None,
        "filterOptionName": "filter_" + short_id(subject, operator, str(comparator)),
    }


def eq(column: str, value) -> dict:
    return _filter(column, "==", value)


def not_null(column: str) -> dict:
    return _filter(column, "IS NOT NULL")


BRANDED = eq("branded_str", "Branded")
UNBRANDED = eq("branded_str", "Unbranded")
TWDC = eq("twdc_int", 1)
# Lets the dashboard "Fecha" filter drive every chart.
TIME_RANGE = _filter("date_dte", "TEMPORAL_RANGE", "No filter")


def _base(viz_type: str, filters) -> dict:
    return {
        "viz_type": viz_type,
        "adhoc_filters": [TIME_RANGE, *filters],
        "extra_form_data": {},
        "dashboards": [],
    }


_ECHARTS_COMMON = {
    "metrics": [METRIC],
    "order_desc": True,
    "truncate_metric": True,
    "show_empty_columns": True,
    "comparison_type": "values",
    "annotation_layers": [],
    "forecastPeriods": 10,
    "forecastInterval": 0.8,
    "x_axis_title_margin": 15,
    "y_axis_title_margin": 15,
    "y_axis_title_position": "Left",
    "sort_series_type": "sum",
    "color_scheme": "supersetColors",
    "only_total": True,
    "legendType": "scroll",
    "legendOrientation": "bottom",
    "x_axis_time_format": "smart_date",
    "y_axis_format": "SMART_NUMBER",
    "truncateXAxis": True,
    "y_axis_bounds": [None, None],
    "rich_tooltip": True,
    "tooltipTimeFormat": "smart_date",
    "show_value": True,
    "timeseries_limit_metric": METRIC,
}


def bar(
    x: str,
    *,
    filters=(),
    groupby: str | None = None,
    limit: int = 10,
    horizontal: bool = False,
    percent: bool = False,
    series_limit: int = 10,
) -> dict:
    """Bar chart over a categorical axis: top ``limit`` values, or stacked by ``groupby``."""
    params = _base("echarts_timeseries_bar", filters)
    params.update(_ECHARTS_COMMON)
    params.update(
        {
            "x_axis": x,
            "time_grain_sqla": "P1D",
            "groupby": [groupby] if groupby else [],
            "orientation": "horizontal" if horizontal else "vertical",
            "xAxisLabelRotation": 0 if horizontal else 45,
            "show_legend": bool(groupby),
        }
    )
    if groupby:
        params.update(
            {
                "row_limit": 10000,
                "limit": series_limit,
                "stack": "Stack",
                "contributionMode": "row" if percent else None,
                "y_axis_format": ".0%" if percent else "SMART_NUMBER",
                "x_axis_sort_series": "sum",
                "x_axis_sort_series_ascending": False,
            }
        )
    else:
        params.update(
            {
                "row_limit": limit,
                "stack": None,
                # Horizontal bars are drawn bottom-up: ascending puts the largest on top.
                "x_axis_sort": METRIC,
                "x_axis_sort_asc": horizontal,
            }
        )
    return params


def line(*, filters=(), groupby: str | None = None, series_limit: int = 10) -> dict:
    """Weekly evolution (the dashboard "Timeframe" filter switches it to monthly)."""
    params = _base("echarts_timeseries_line", filters)
    params.update(_ECHARTS_COMMON)
    params.update(
        {
            "x_axis": "date_dte",
            "time_grain_sqla": "P1W",
            "x_axis_sort_asc": True,
            "x_axis_sort_series": "name",
            "x_axis_sort_series_ascending": True,
            "groupby": [groupby] if groupby else [],
            "limit": series_limit if groupby else None,
            "row_limit": 10000,
            "seriesType": "line",
            "opacity": 0.2,
            "markerEnabled": True,
            "markerSize": 6,
            "show_legend": bool(groupby),
            "zoomable": False,
        }
    )
    return params


def pie(column: str, *, filters=(), limit: int = 25) -> dict:
    params = _base("pie", filters)
    params.update(
        {
            "groupby": [column],
            "metric": METRIC,
            "row_limit": limit,
            "sort_by_metric": True,
            "color_scheme": "supersetColors",
            "show_labels_threshold": 3,
            "show_legend": True,
            "legendType": "scroll",
            "legendOrientation": "right",
            # Names are in the legend; the slices show their share (fits narrow columns).
            "label_type": "percent",
            "number_format": "SMART_NUMBER",
            "date_format": "smart_date",
            "show_labels": True,
            "labels_outside": True,
            "label_line": True,
            "outerRadius": 70,
            "donut": True,
            "innerRadius": 40,
            "show_total": False,
        }
    )
    return params


def treemap(column: str, *, filters=(), limit: int = 50) -> dict:
    params = _base("treemap_v2", filters)
    params.update(
        {
            "groupby": [column],
            "metric": METRIC,
            "row_limit": limit,
            "sort_by_metric": True,
            "color_scheme": "supersetColors",
            "show_labels": True,
            "show_upper_labels": True,
            "label_type": "key_value",
            "number_format": "SMART_NUMBER",
            "date_format": "smart_date",
        }
    )
    return params


def word_cloud(column: str, *, filters=(), limit: int = 50) -> dict:
    params = _base("word_cloud", filters)
    params.update(
        {
            "series": column,
            "metric": METRIC,
            "row_limit": limit,
            # Without it the query has no ORDER BY and the limit keeps arbitrary words.
            "sort_by_metric": True,
            "size_from": 12,
            "size_to": 60,
            "rotation": "flat",
            "color_scheme": "supersetColors",
        }
    )
    return params


def table(*columns: str, filters=(), limit: int = 100, percent: bool = False) -> dict:
    params = _base("table", filters)
    params.update(
        {
            "query_mode": "aggregate",
            "groupby": list(columns),
            "metrics": [METRIC],
            "all_columns": [],
            "percent_metrics": [METRIC] if percent else [],
            "order_by_cols": [],
            "row_limit": limit,
            "server_page_length": 10,
            "order_desc": True,
            "table_timestamp_format": "smart_date",
            "show_cell_bars": True,
            "color_pn": True,
            "include_search": False,
            "allow_rearrange_columns": False,
            "conditional_formatting": [],
        }
    )
    return params


# --------------------------------------------------------------------------------------
# Charts, by tab (titles as in the Revenue Research report).
# --------------------------------------------------------------------------------------

COMPANY = "group_company_owner_rights_str"
COUNTRIES = ("Argentina", "Brasil", "Colombia", "Chile", "Mexico")

CHARTS: dict[str, tuple[str, dict]] = {
    # Summary
    "sum_branded_pie": ("Búsquedas Branded / Unbranded", pie("branded_str")),
    "sum_top10_categories": ("Categorías - Top 10 Total Trends", bar("category_str")),
    "sum_top10_categories_branded": ("Categorías - Top 10 Branded", bar("category_str", filters=[BRANDED])),
    "sum_franchise_pie": ("Búsquedas Franquicias", pie("franquicia_si_no_str")),
    "sum_top10_brands": ("TOP 10 Marcas", bar("brand_str", filters=[not_null("brand_str")], horizontal=True)),
    "sum_top10_franchises": (
        "TOP 10 Franquicias (Nivel 1)",
        bar("franchise_n1_str", filters=[not_null("franchise_n1_str")], horizontal=True),
    ),
    "sum_top10_characters": (
        "TOP 10 Personajes",
        bar("character_str", filters=[not_null("character_str")], horizontal=True),
    ),
    "sum_top25_unbranded": (
        "Top 25 de Tendencias",
        table("lemmatized_keyword_str", filters=[UNBRANDED], limit=25),
    ),
    "sum_wordcloud_products": (
        "WordCloud Productos",
        word_cloud(
            "keyword_es_without_stopwords_str",
            filters=[UNBRANDED, not_null("keyword_es_without_stopwords_str")],
            limit=50,
        ),
    ),
    "sum_categories_total": ("Categorías Totales", table("category_str", limit=50)),
    "sum_categories_evolution": ("Evolución de Top Categorías", line(groupby="category_str", series_limit=5)),
    "sum_categories_branded": ("Categorías Totales Branded", table("category_str", filters=[BRANDED], limit=50)),
    "sum_categories_unbranded": (
        "Categorías Totales Unbranded",
        table("category_str", filters=[UNBRANDED], limit=50),
    ),
    # Market Landscape
    "ml_companies_trend": (
        "Tendencias - Principales Compañías",
        line(groupby=COMPANY, filters=[not_null(COMPANY)], series_limit=10),
    ),
    "ml_company_share": ("Share de demanda - Compañía", treemap(COMPANY, filters=[not_null(COMPANY)])),
    "ml_companies_by_country": (
        "Compañías por País",
        bar("country_str", groupby=COMPANY, filters=[not_null(COMPANY)], series_limit=10),
    ),
    "ml_branded_categories_share": ("Share categorías brandeadas", treemap("category_str", filters=[BRANDED])),
    "ml_wordcloud_characters": (
        "WordCloud Personajes",
        word_cloud("character_str", filters=[not_null("character_str")], limit=50),
    ),
    "ml_categories_by_company": (
        "Categorías por compañía",
        bar("category_str", groupby=COMPANY, filters=[not_null(COMPANY)], series_limit=10),
    ),
    "ml_top5_brands_twdc": (
        "TOP 5 - Marcas asociadas a TWDC",
        bar("brand_str", filters=[TWDC, not_null("brand_str")], limit=5, horizontal=True),
    ),
    # Franchise (The Walt Disney Company)
    "fr_twdc_trend": (
        "Tendencias - Franquicias TWDC (Nivel 1)",
        line(groupby="franchise_n1_str", filters=[TWDC], series_limit=10),
    ),
    "fr_n1_by_country": (
        "Franquicias por país (Nivel 1)",
        bar("country_str", groupby="franchise_n1_str", filters=[TWDC]),
    ),
    "fr_categories_by_n1": (
        "Principales categorías por franquicias (Nivel 1)",
        bar("franchise_n1_str", groupby="category_str", filters=[TWDC], series_limit=5),
    ),
    "fr_n1_by_n2": (
        "Franquicias (Nivel 1) por Franquicias (Nivel 2)",
        bar("franchise_n1_str", groupby="franchise_n2_str", filters=[TWDC], percent=True, series_limit=25),
    ),
    "fr_n2_share": ("Share por Franquicias (Nivel 2)", treemap("franchise_n2_str", filters=[TWDC])),
    "fr_n2_by_country": (
        "Franquicias (Nivel 2) por país",
        bar("country_str", groupby="franchise_n2_str", filters=[TWDC], series_limit=15),
    ),
    "fr_n2_by_content": (
        "Franquicias (Nivel 2) por Contenido",
        bar("franchise_n2_str", groupby="content_str", filters=[TWDC], percent=True, series_limit=25),
    ),
    # Categories
    "cat_branded_by_country": (
        "Tendencias de búsquedas brandeadas por país",
        line(groupby="country_str", filters=[BRANDED]),
    ),
    "cat_company_share": ("Share por Compañía", treemap(COMPANY, filters=[not_null(COMPANY)])),
    "cat_companies_by_country": (
        "Compañías por País",
        bar("country_str", groupby=COMPANY, filters=[not_null(COMPANY)], series_limit=15),
    ),
    "cat_n1_pie": ("Franquicias Nivel 1", pie("franchise_n1_str", filters=[TWDC])),
    "cat_n2_by_country": (
        "Franquicias Nivel 2 por país",
        bar("country_str", groupby="franchise_n2_str", filters=[TWDC], series_limit=15),
    ),
    "cat_top10_branded_keywords": (
        "Top 10 de Tendencias Branded en la categoría",
        bar("keyword_str", filters=[BRANDED], horizontal=True),
    ),
    "cat_wordcloud_top20_characters": (
        "Personajes - Top 20",
        word_cloud("character_str", filters=[not_null("character_str")], limit=20),
    ),
    # Subcategories
    "sub_top10": ("TOP 10 Subcategorías", bar("subcategory_str", horizontal=True)),
    "sub_top10_evolution": ("Evolución TOP 10 Subcategorías", line(groupby="subcategory_str", series_limit=10)),
    **{
        f"sub_top5_{country.lower()}": (
            f"{country} - TOP 5 Subcategorías",
            bar("subcategory_str", filters=[eq("country_str", country)], limit=5),
        )
        for country in COUNTRIES
    },
    "sub_wordcloud_branded": (
        "Branded - Top 25 Productos",
        word_cloud("producto_str", filters=[BRANDED, not_null("producto_str")], limit=25),
    ),
    "sub_wordcloud_unbranded": (
        "Unbranded - Top 25 Productos",
        word_cloud("producto_str", filters=[UNBRANDED, not_null("producto_str")], limit=25),
    ),
    "sub_twdc_table": ("Subcategorías TWDC", table("subcategory_str", filters=[TWDC], limit=100)),
    "sub_twdc_evolution": (
        "Subcategorías TWDC - Evolución",
        line(groupby="subcategory_str", filters=[TWDC], series_limit=10),
    ),
    "sub_by_franchise": (
        "Subcategorías por Franquicia",
        bar("franchise_n1_str", groupby="subcategory_str", filters=[TWDC], series_limit=15),
    ),
    "sub_total_table": ("Subcategorías Totales", table("subcategory_str", limit=200)),
    "sub_branded_table": ("Subcategorías Branded", table("subcategory_str", filters=[BRANDED], limit=200)),
    "sub_unbranded_table": ("Subcategorías Unbranded", table("subcategory_str", filters=[UNBRANDED], limit=200)),
    # Products and Trends
    "prod_branded_pie": ("Branded / Unbranded", pie("branded_str")),
    "prod_franchises_treemap": (
        "Franquicias Brandeadas",
        treemap("franchise_n1_str", filters=[not_null("franchise_n1_str")]),
    ),
    "prod_top100_products": (
        "Top 100 de productos buscados",
        table("producto_str", filters=[not_null("producto_str")], limit=100, percent=True),
    ),
    "prod_branded_product_character": (
        "Producto branded y personaje",
        table(
            "character_str",
            "producto_str",
            filters=[not_null("character_str"), not_null("producto_str")],
            limit=100,
        ),
    ),
    "prod_top10_trends": ("Top 10 en Tendencias", bar("keyword_es_without_stopwords_str")),
    "prod_words_in_n2": (
        "Palabras buscadas dentro de franquicias Nivel 2 TOP 20",
        treemap("producto_str", filters=[not_null("franchise_n2_str"), not_null("producto_str")], limit=20),
    ),
}

README_MD = """### Condiciones Generales

Se descargan **diariamente las tendencias de Mercado Libre** para las subcategorías seleccionadas
del portal, de los países **Argentina, Brasil, Chile, Colombia y México**.

**Landscape competitivo:** para clasificar las tendencias y encontrar oportunidades de negocio se
usa un glosario de:

- **Franquicias:** Empresa/owner, Contenido, Personajes.
- **Marcas:** participación de las marcas en relación a las franquicias.

#### Objetivos por pestaña

- **Summary:** mirada inicial del mercado de búsquedas.
- **Market Landscape:** posicionamiento de TWDC en el mercado competitivo.
- **Franchise:** visualización y relevancia de las franquicias de TWDC.
- **Categories:** apertura por categoría comercial de la información relevada.
- **Subcategories:** subcategorías dentro de las categorías.
- **Products and Trends:** relevancia de los sustantivos buscados.

#### Consideraciones generales

- **Búsquedas:** cantidad de veces que una keyword aparece en las tendencias (keyword × subcategoría × día).
- **Branded:** tendencia que tiene una empresa / contenido / franquicia / personaje y/o marca.
- **Fecha:** por defecto se agrupa en semanas, representadas con la fecha del día lunes
  (filtro *Timeframe* para pasar a meses).
- **Franquicias:** consideran marcas con contenidos (Barbie, Lego, similar).
- **Grupo Empresa Owner Derechos:** clasificación general de la empresa dueña de los derechos.
- **Franquicia Nivel 1:** clasificación de franquicias de marketing.
- **Franquicia Nivel 2:** incluye todas las aperturas desde sagas.
- **Contenido:** desagrega donde es posible las sagas por película u otro tipo de contenido.
- **Producto:** primer sustantivo de la búsqueda (lematizado), sin la marca ni el personaje.

Datos: tabla `mdm_revenue_research_meli.trends` (dbt), actualizada todos los días por Dagster.
"""

# Layout: tab -> rows. A row is a list of (chart key, width) or ("#header", text) / ("#md", text, height).
CHART_HEIGHT = 56
TABS = [
    ("Read Me", [[("#md", README_MD, 110)]]),
    (
        "Summary",
        [
            [("#header", "Summary - Total Trends")],
            [("sum_branded_pie", 4), ("sum_top10_categories", 8)],
            [("#header", "Branded Trends")],
            [("sum_top10_categories_branded", 8), ("sum_franchise_pie", 4)],
            [("sum_top10_brands", 4), ("sum_top10_franchises", 4), ("sum_top10_characters", 4)],
            [("#header", "Unbranded Trends")],
            [("sum_top25_unbranded", 6), ("sum_wordcloud_products", 6)],
            [("sum_categories_total", 12)],
            [("sum_categories_evolution", 12)],
            [("sum_categories_branded", 6), ("sum_categories_unbranded", 6)],
            [("#md", SOURCE_NOTE, 8)],
        ],
    ),
    (
        "Market Landscape",
        [
            [("#header", "Market Landscape")],
            [("ml_companies_trend", 12)],
            [("ml_company_share", 6), ("ml_companies_by_country", 6)],
            [("ml_branded_categories_share", 6), ("ml_wordcloud_characters", 6)],
            [("ml_categories_by_company", 12)],
            [("ml_top5_brands_twdc", 12)],
            [("#md", SOURCE_NOTE, 8)],
        ],
    ),
    (
        "Franchise",
        [
            [("#header", "Franquicias")],
            [("fr_twdc_trend", 12)],
            [("fr_n1_by_country", 6), ("fr_categories_by_n1", 6)],
            [("fr_n1_by_n2", 6), ("fr_n2_share", 6)],
            [("fr_n2_by_country", 6), ("fr_n2_by_content", 6)],
            [("#md", SOURCE_NOTE, 8)],
        ],
    ),
    (
        "Categories",
        [
            [("#header", "Categoría")],
            [("cat_branded_by_country", 12)],
            [("cat_company_share", 6), ("cat_companies_by_country", 6)],
            [("cat_n1_pie", 6), ("cat_n2_by_country", 6)],
            [("cat_top10_branded_keywords", 6), ("cat_wordcloud_top20_characters", 6)],
            [("#md", SOURCE_NOTE, 8)],
        ],
    ),
    (
        "Subcategories",
        [
            [("#header", "Subcategorías")],
            [("sub_top10", 12)],
            [("sub_top10_evolution", 12)],
            [("#header", "Por País TOP 5")],
            [("sub_top5_argentina", 4), ("sub_top5_brasil", 4), ("sub_top5_colombia", 4)],
            [("sub_top5_chile", 6), ("sub_top5_mexico", 6)],
            [("#header", "Wordcloud Top 25 Keywords")],
            [("sub_wordcloud_branded", 6), ("sub_wordcloud_unbranded", 6)],
            [("#header", "Subcategorías TWDC")],
            [("sub_twdc_table", 6), ("sub_by_franchise", 6)],
            [("sub_twdc_evolution", 12)],
            [("sub_total_table", 4), ("sub_branded_table", 4), ("sub_unbranded_table", 4)],
            [("#md", SOURCE_NOTE, 8)],
        ],
    ),
    (
        "Products and Trends",
        [
            [("#header", "Producto y tendencias")],
            [("prod_branded_pie", 6), ("prod_franchises_treemap", 6)],
            [("prod_top100_products", 6), ("prod_branded_product_character", 6)],
            [("prod_top10_trends", 12)],
            [("prod_words_in_n2", 12)],
            [("#md", SOURCE_NOTE, 8)],
        ],
    ),
]

# --------------------------------------------------------------------------------------
# Native filters (filter bar on top, as in the report).
# --------------------------------------------------------------------------------------

SELECT_FILTERS = [
    ("País", "country_str"),
    ("Categoría", "category_str"),
    ("Subcategoría", "subcategory_str"),
    ("Grupo Empresa Owner Derechos", COMPANY),
    ("Franquicia", "franchise_n1_str"),
    ("Contenido", "content_str"),
    ("Personaje", "character_str"),
    ("Marca", "brand_str"),
    ("Branded", "branded_str"),
]

# Brand, character and franchise columns are only filled on Branded searches, so filtering by
# them (in the filter bar or by clicking a chart) would always blank the charts pinned to
# Unbranded: those charts ignore such filters. Charts pinned to either value ignore the
# Branded filter itself.
BRANDED_ONLY_COLUMNS = {
    "brand_str",
    "second_brand_str",
    "character_str",
    COMPANY,
    "franchise_n1_str",
    "franchise_n2_str",
    "franchise_n3_str",
    "content_str",
    "twdc_int",
    "franquicia_si_no_str",
}


def pinned_branded(params: dict) -> str | None:
    """The Branded/Unbranded value a chart is restricted to, if any."""
    for adhoc in params["adhoc_filters"]:
        if adhoc["subject"] == "branded_str" and adhoc["operator"] == "==":
            return adhoc["comparator"]
    return None


def immune_charts(column: str, chart_ids: dict[str, int]) -> list[int]:
    """Charts that a filter on ``column`` must not apply to (see BRANDED_ONLY_COLUMNS)."""
    if column == "branded_str":
        return [chart_ids[key] for key, (_, params) in CHARTS.items() if pinned_branded(params)]
    if column in BRANDED_ONLY_COLUMNS:
        return [
            chart_ids[key] for key, (_, params) in CHARTS.items() if pinned_branded(params) == "Unbranded"
        ]
    return []


def native_filters(chart_ids: dict[str, int]) -> list[dict]:
    scope_all = {"rootPath": ["ROOT_ID"], "excluded": []}
    common = {"type": "NATIVE_FILTER", "description": "", "cascadeParentIds": []}
    filters = [
        {
            **common,
            "id": "NATIVE_FILTER-fecha",
            "name": "Fecha",
            "filterType": "filter_time",
            "targets": [{}],
            "controlValues": {"enableEmptyFilter": False},
            "defaultDataMask": {"extraFormData": {}, "filterState": {}, "ownState": {}},
            "scope": scope_all,
        },
        {
            **common,
            "id": "NATIVE_FILTER-timeframe",
            "name": "Timeframe",
            "filterType": "filter_timegrain",
            "targets": [{"datasetUuid": DATASET_UUID}],
            "controlValues": {"enableEmptyFilter": False},
            "defaultDataMask": {
                "extraFormData": {"time_grain_sqla": "P1W"},
                "filterState": {"value": ["P1W"]},
                "ownState": {},
            },
            # Only the evolution (line) charts have a time axis.
            "scope": {
                "rootPath": ["ROOT_ID"],
                "excluded": [
                    chart_ids[key]
                    for key, (_, params) in CHARTS.items()
                    if params["viz_type"] != "echarts_timeseries_line"
                ],
            },
        },
    ]
    for name, column in SELECT_FILTERS:
        filter_id = "NATIVE_FILTER-" + re.sub(r"[^a-z0-9]+", "-", column.lower()).strip("-")
        filters.append(
            {
                **common,
                "id": filter_id,
                "name": name,
                "filterType": "filter_select",
                "targets": [{"column": {"name": column}, "datasetUuid": DATASET_UUID}],
                "controlValues": {
                    "enableEmptyFilter": False,
                    "defaultToFirstItem": False,
                    "multiSelect": True,
                    "searchAllOptions": False,
                    "inverseSelection": False,
                },
                "defaultDataMask": {"extraFormData": {}, "filterState": {}, "ownState": {}},
                "scope": {"rootPath": ["ROOT_ID"], "excluded": immune_charts(column, chart_ids)},
            }
        )
    # Subcategory options follow the selected categories.
    by_id = {f["name"]: f for f in filters}
    by_id["Subcategoría"]["cascadeParentIds"] = [by_id["Categoría"]["id"]]
    return filters


def cross_filter_configuration(chart_ids: dict[str, int]) -> dict:
    """Cross-filter scope of the charts whose clicks filter a column some charts must ignore.

    The other charts keep the default (global) scope. provision.py maps these placeholder ids
    to the imported ones, which the Superset importer does not do for chart_configuration.
    """
    configuration = {}
    for key, (_, params) in CHARTS.items():
        dimensions = {params.get("x_axis"), params.get("series"), *params.get("groupby", [])}
        excluded = sorted({chart for column in dimensions if column for chart in immune_charts(column, chart_ids)})
        if excluded:
            chart_id = chart_ids[key]
            configuration[str(chart_id)] = {
                "id": chart_id,
                "crossFilters": {"scope": {"rootPath": ["ROOT_ID"], "excluded": excluded}},
            }
    return configuration


# --------------------------------------------------------------------------------------
# Assembly.
# --------------------------------------------------------------------------------------


def chart_file(key: str) -> str:
    title = CHARTS[key][0]
    slug = re.sub(r"[^A-Za-z0-9]+", "_", title).strip("_")
    return f"charts/{slug}_{short_id('chart', key)[:6]}.yaml"


def chart_config(key: str) -> dict:
    title, params = CHARTS[key]
    return {
        "slice_name": title,
        "description": None,
        "certified_by": None,
        "certification_details": None,
        "viz_type": params["viz_type"],
        "params": params,
        "query_context": None,
        "cache_timeout": None,
        "uuid": uid("chart", key),
        "version": VERSION,
        "dataset_uuid": DATASET_UUID,
    }


def position(chart_ids: dict[str, int]) -> dict:
    pos: dict = {
        "DASHBOARD_VERSION_KEY": "v2",
        "ROOT_ID": {"type": "ROOT", "id": "ROOT_ID", "children": ["TABS-main"]},
        "HEADER_ID": {"id": "HEADER_ID", "type": "HEADER", "meta": {"text": DASHBOARD_TITLE}},
        "TABS-main": {"type": "TABS", "id": "TABS-main", "children": [], "parents": ["ROOT_ID"], "meta": {}},
    }
    used: set[str] = set()
    for tab_title, rows in TABS:
        tab_id = "TAB-" + short_id("tab", tab_title)
        tab_parents = ["ROOT_ID", "TABS-main"]
        pos["TABS-main"]["children"].append(tab_id)
        pos[tab_id] = {
            "type": "TAB",
            "id": tab_id,
            "children": [],
            "parents": tab_parents,
            "meta": {"text": tab_title, "defaultText": "Tab title", "placeholder": "Tab title"},
        }
        for row_index, row in enumerate(rows):
            if row[0][0] == "#header":
                header_id = "HEADER-" + short_id(tab_title, str(row_index))
                pos[tab_id]["children"].append(header_id)
                pos[header_id] = {
                    "type": "HEADER",
                    "id": header_id,
                    "children": [],
                    "parents": [*tab_parents, tab_id],
                    "meta": {
                        "text": row[0][1],
                        "headerSize": "MEDIUM_HEADER",
                        "background": "BACKGROUND_TRANSPARENT",
                    },
                }
                continue
            row_id = "ROW-" + short_id(tab_title, str(row_index))
            row_parents = [*tab_parents, tab_id]
            pos[tab_id]["children"].append(row_id)
            pos[row_id] = {
                "type": "ROW",
                "id": row_id,
                "children": [],
                "parents": row_parents,
                "meta": {"background": "BACKGROUND_TRANSPARENT"},
            }
            assert sum(item[1] if item[0] != "#md" else 12 for item in row) <= 12, (tab_title, row)
            for item in row:
                if item[0] == "#md":
                    md_id = "MARKDOWN-" + short_id(tab_title, str(row_index), "md")
                    pos[row_id]["children"].append(md_id)
                    pos[md_id] = {
                        "type": "MARKDOWN",
                        "id": md_id,
                        "children": [],
                        "parents": [*row_parents, row_id],
                        "meta": {"width": 12, "height": item[2], "code": item[1]},
                    }
                    continue
                key, width = item
                assert key not in used, f"chart {key} placed twice"
                used.add(key)
                chart_id = "CHART-" + short_id("chart", key)
                pos[row_id]["children"].append(chart_id)
                pos[chart_id] = {
                    "type": "CHART",
                    "id": chart_id,
                    "children": [],
                    "parents": [*row_parents, row_id],
                    "meta": {
                        "width": width,
                        "height": CHART_HEIGHT,
                        "chartId": chart_ids[key],
                        "uuid": uid("chart", key),
                        "sliceName": CHARTS[key][0],
                    },
                }
    missing = set(CHARTS) - used
    assert not missing, f"charts not placed on the dashboard: {sorted(missing)}"
    return pos


def dashboard_config() -> dict:
    # Placeholder ids; the importer maps them to the real ones through the chart UUIDs.
    chart_ids = {key: index for index, key in enumerate(CHARTS, start=1)}
    return {
        "dashboard_title": DASHBOARD_TITLE,
        "description": None,
        "css": "",
        "slug": DASHBOARD_SLUG,
        "certified_by": None,
        "certification_details": None,
        "published": True,
        "uuid": DASHBOARD_UUID,
        "position": position(chart_ids),
        "metadata": {
            "native_filter_configuration": native_filters(chart_ids),
            "chart_configuration": cross_filter_configuration(chart_ids),
            "global_chart_configuration": {"scope": {"rootPath": ["ROOT_ID"], "excluded": []}},
            "color_scheme": "supersetColors",
            "refresh_frequency": 0,
            "expanded_slices": {},
            "label_colors": {},
            "shared_label_colors": {},
            "color_scheme_domain": [],
            "cross_filters_enabled": True,
            "filter_bar_orientation": "HORIZONTAL",
            "timed_refresh_immune_slices": [],
            "default_filters": "{}",
        },
        "version": VERSION,
    }


def write(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.safe_dump(data, sort_keys=False, allow_unicode=True, width=1000), encoding="utf-8"
    )


def main() -> None:
    if OUT_DIR.exists():
        shutil.rmtree(OUT_DIR)
    write(OUT_DIR / "metadata.yaml", {"version": VERSION, "type": "assets", "timestamp": "2026-10-30T00:00:00+00:00"})
    write(OUT_DIR / "databases" / "MeLi_Trends_PostgreSQL.yaml", database_config())
    write(OUT_DIR / "datasets" / "MeLi_Trends_PostgreSQL" / "trends.yaml", dataset_config())
    for key in CHARTS:
        write(OUT_DIR / chart_file(key), chart_config(key))
    write(OUT_DIR / "dashboards" / "Revenue_Research_Mercado_Libre_Trends.yaml", dashboard_config())
    print(f"Wrote {len(CHARTS)} charts to {OUT_DIR}")


if __name__ == "__main__":
    main()
