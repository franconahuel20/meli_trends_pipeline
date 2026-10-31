{{
    config(
        materialized='incremental',
        alias='trends',
        incremental_strategy='delete+insert',
        unique_key='date_dte',
        on_schema_change='append_new_columns',
        indexes=[
            {'columns': ['date_dte']},
            {'columns': ['country_str', 'date_dte']},
        ],
    )
}}

-- Final table: the staging table meli_trends_l3 in the business layout of the `trends`
-- extract (same columns and order). The matching audit trail stays in staging.

with staging as (

    select *
    from {{ source('stg_revenue_research_meli', 'meli_trends_l3') }}
    {% if is_incremental() %}
    -- Only the snapshot dates (re)loaded into staging after their last build here: a new
    -- day, a same-day re-run, or history re-matched after a reference/word-list change.
    where date_dte in (
        select s.date_dte
        from {{ source('stg_revenue_research_meli', 'meli_trends_l3') }} as s
        left join (
            select date_dte, max(loading_dtm) as loading_dtm
            from {{ this }}
            group by date_dte
        ) as t on t.date_dte = s.date_dte
        group by s.date_dte, t.loading_dtm
        having t.loading_dtm is null or max(s.loading_dtm) > t.loading_dtm
    )
    {% endif %}

)

select
    cast(keyword_str as varchar(1000)) as keyword_str,
    cast(url_str as varchar(3000)) as url_str,
    cast(date_dte as date) as date_dte,
    cast(country_str as varchar(200)) as country_str,
    cast(category_str as varchar(200)) as category_str,
    cast(subcategory_str as varchar(200)) as subcategory_str,
    cast(_internal_filename_str as varchar(300)) as _internal_filename_str,
    loading_dtm,
    cast(file_row_id_int as integer) as file_row_id_int,
    cast(brand_str as varchar(200)) as brand_str,
    cast(character_str as varchar(200)) as character_str,
    cast(second_brand_str as varchar(200)) as second_brand_str,
    cast(group_company_owner_rights_str as varchar(500)) as group_company_owner_rights_str,
    cast(twdc_int as integer) as twdc_int,
    cast(franchise_n1_str as varchar(200)) as franchise_n1_str,
    cast(franchise_n2_str as varchar(200)) as franchise_n2_str,
    cast(franchise_n3_str as varchar(200)) as franchise_n3_str,
    cast(content_str as varchar(300)) as content_str,
    cast(keyword_in_spanish_str as varchar(1000)) as keyword_in_spanish_str,
    cast(date_trunc('week', date_dte) as date) as week_dte,
    cast(normalized_keyword_es_str as varchar(1000)) as normalized_keyword_es_str,
    cast(keyword_es_without_stopwords_str as varchar(1000)) as keyword_es_without_stopwords_str,
    cast(character_without_stopwords_str as varchar(200)) as character_without_stopwords_str,
    cast(lemmatized_keyword_str as varchar(1000)) as lemmatized_keyword_str,
    cast(nouns_keyword_str as varchar(1000)) as nouns_keyword_str,
    cast(has_franchise_n2_str as varchar(5)) as has_franchise_n2_str,
    cast(has_franchise_n3_str as varchar(5)) as has_franchise_n3_str,
    cast(has_character_str as varchar(5)) as has_character_str,
    cast(has_franchise_n1_str as varchar(5)) as has_franchise_n1_str,
    cast(has_brand_str as varchar(5)) as has_brand_str,
    cast(branded_str as varchar(20)) as branded_str,
    cast(year_calendar_int as integer) as year_calendar_int,
    cast(month_calendar_int as integer) as month_calendar_int,
    cast(day_calendar_int as integer) as day_calendar_int
from staging
