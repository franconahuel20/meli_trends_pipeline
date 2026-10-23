from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd

from meli_trends_pipeline.matching import L3_COLUMNS, enrich_trends


def test_enrich_trends_builds_the_l3_layout(real_matcher):
    l2 = pd.DataFrame(
        {
            "keyword_str": ["Zapatillas Nike", "mochila de Stitch", "termo 1 litro", "funda samsung xiaomi"],
            "url_str": ["https://example.com/a", "https://example.com/b", None, None],
            "date_dte": ["2026-10-22"] * 4,
            "country_str": ["Argentina", "Mexico", "Chile", "Colombia"],
            "category_str": ["Ropa y Accesorios"] * 4,
            "subcategory_str": ["Calzado"] * 4,
        }
    )
    loaded_at = datetime(2026, 10, 22, 23, 5, tzinfo=ZoneInfo("America/Argentina/Buenos_Aires"))
    l3 = enrich_trends(l2, real_matcher, loaded_at)

    assert list(l3.columns) == list(L3_COLUMNS)
    assert len(l3) == 4
    nike, stitch, termo, phones = (row for _, row in l3.iterrows())

    assert nike["brand_str"] == "nike" and nike["brand_match_method_str"] == "exact"
    assert nike["branded_str"] == "Branded" and nike["has_brand_str"] == "YES"
    assert nike["nouns_keyword_str"] == "zapatillas"

    assert stitch["character_str"] == "Stitch"
    assert stitch["franchise_n1_str"] == "Disney" and stitch["twdc_int"] == 1
    assert stitch["has_character_str"] == "YES" and stitch["has_franchise_n1_str"] == "YES"
    assert stitch["keyword_es_without_stopwords_str"] == "mochila stitch"
    assert stitch["nouns_keyword_str"] == "mochila"

    assert termo["branded_str"] == "Unbranded"
    assert pd.isna(termo["brand_str"]) and pd.isna(termo["character_str"])
    assert termo["group_company_owner_rights_str"] is None and termo["twdc_int"] == 0

    assert phones["brand_str"] == "samsung" and phones["second_brand_str"] == "xiaomi"

    assert str(l3["date_dte"].iloc[0]) == "2026-10-22"
    assert l3["year_calendar_int"].tolist() == [2026] * 4
    assert l3["file_row_id_int"].tolist() == [1, 2, 3, 4]
    assert l3["loading_dtm"].iloc[0] == pd.Timestamp(loaded_at)
