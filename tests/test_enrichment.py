from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd

from meli_trends_pipeline.matching import L3_COLUMNS, enrich_trends
from meli_trends_pipeline.matching.enrichment import display_name
from meli_trends_pipeline.matching.linguistics import Token, language_of


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

    assert nike["brand_str"] == "Nike" and nike["brand_match_method_str"] == "exact"
    assert nike["branded_str"] == "Branded" and nike["has_brand_str"] == "YES"
    assert nike["nouns_keyword_str"] == "zapatillas"
    assert nike["lemmatized_keyword_str"] == "zapatillas nike"

    assert stitch["character_str"] == "Stitch"
    assert stitch["franchise_n1_str"] == "Disney" and stitch["twdc_int"] == 1
    assert stitch["has_character_str"] == "YES" and stitch["has_franchise_n1_str"] == "YES"
    assert stitch["keyword_es_without_stopwords_str"] == "mochila stitch"
    assert stitch["nouns_keyword_str"] == "mochila"

    assert termo["branded_str"] == "Unbranded"
    assert pd.isna(termo["brand_str"]) and pd.isna(termo["character_str"])
    assert termo["group_company_owner_rights_str"] is None and termo["twdc_int"] == 0
    assert termo["nouns_keyword_str"] == "termo litro"

    assert phones["brand_str"] == "Samsung" and phones["second_brand_str"] == "Xiaomi"

    assert str(l3["date_dte"].iloc[0]) == "2026-10-22"
    assert l3["year_calendar_int"].tolist() == [2026] * 4
    assert l3["file_row_id_int"].tolist() == [0, 1, 2, 3]
    assert l3["_internal_filename_str"].isna().all()
    assert l3["loading_dtm"].iloc[0] == pd.Timestamp(loaded_at)


def _l2(rows, **extra):
    df = pd.DataFrame(
        rows, columns=["keyword_str", "country_str", "category_str"]
    ).assign(url_str=None, date_dte="2026-10-30", subcategory_str="x", **extra)
    return df


def test_category_rules_master_list_priority_and_lineage(real_matcher):
    l2 = _l2(
        [
            ("raqueta wilson", "Argentina", "Deportes y Fitness"),
            ("separadores wilson jones", "Argentina", "Arte, Librería y Mercería"),
            ("notebook dell core i7", "Mexico", "Computación"),
            ("cable iphone apple", "Chile", "Celulares y Teléfonos"),
        ],
        _internal_filename_str="mercado_libre_trends_30102026.csv",
        file_row_id_int=[10, 11, 15, 20],
    )
    l3 = enrich_trends(l2, real_matcher, datetime(2026, 10, 30, 23, 0))
    wilson, jones, dell, iphone = (row for _, row in l3.iterrows())

    assert wilson["brand_str"] == "Wilson" and wilson["branded_str"] == "Branded"
    assert pd.isna(jones["brand_str"])
    # A brand named as such comes before the product line it uses.
    assert dell["brand_str"] == "Dell" and dell["second_brand_str"] == "Intel"
    # "iphone" and "apple" name the same brand once.
    assert iphone["brand_str"] == "Apple" and pd.isna(iphone["second_brand_str"])
    assert iphone["nouns_keyword_str"] == "cable"

    assert l3["file_row_id_int"].tolist() == [10, 11, 15, 20]
    assert (l3["_internal_filename_str"] == "mercado_libre_trends_30102026.csv").all()


class _FakeAnalyzer:
    """Tags every word as a noun with an upper-cased lemma and records the language used."""

    def __init__(self):
        self.calls = []

    def analyze(self, texts, language):
        self.calls.append((language, list(texts)))
        return [[Token(w, w.upper(), "NOUN") for w in t.split()] for t in texts]


def test_analyzer_gets_the_language_of_each_country(real_matcher):
    analyzer = _FakeAnalyzer()
    l2 = _l2(
        [("carrinho de brinquedo", "Brasil", "Juegos y Juguetes"), ("Auto de Juguete", "Mexico", "Juegos y Juguetes")]
    )
    l3 = enrich_trends(l2, real_matcher, datetime(2026, 10, 30), analyzer)
    assert sorted(analyzer.calls) == [("es", ["auto de juguete"]), ("pt", ["carrinho de brinquedo"])]
    assert l3["lemmatized_keyword_str"].tolist() == ["CARRINHO DE BRINQUEDO", "AUTO DE JUGUETE"]
    # Stopwords ("de") never count as nouns.
    assert l3["nouns_keyword_str"].tolist() == ["CARRINHO BRINQUEDO", "AUTO JUGUETE"]


def test_language_of_country():
    assert language_of("Brasil") == "pt"
    assert language_of("Argentina") == "es" and language_of(None) == "es"


def test_display_name():
    assert display_name("new era") == "New Era"
    assert display_name("fisher-price") == "Fisher-Price"
    assert display_name("johnson's") == "Johnson's"
    assert display_name("3m") == "3M"
    assert display_name("Huggies") == "Huggies"
    assert display_name("victoria's secret") == "Victoria's Secret"
