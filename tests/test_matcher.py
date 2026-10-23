"""Unit tests of the matching rules on a small synthetic catalog."""

import pandas as pd
import pytest

from meli_trends_pipeline.matching import MatchingConfig, build_matcher, normalize_text

BRANDS = pd.DataFrame(
    {
        "brand_str": [
            "Samsung", "Nike", "Puma", "HP", "Canon", "Mondial", "Camper", "Power",
            "Power Bank", "Jessica Simpson", "Lego", "Max", "Playstation", "Polo Ralph Lauren", "Polo",
            "Promax", "Elgato", "GoPro", "Big Bang", "Bigbang",
        ],
        "branded_int": [1] * 20,
    }
)
CHARACTERS = pd.DataFrame(
    {
        "character_str": [
            "Spider Man", "Minions", "Anna", "Lisa Simpsons", "Simpson", "Lego Friends",
            "Max Steel", "Igor", "Plants vs Zombies", "Stitch",
        ],
        "group_company_owner_rights_str": [
            "Sony", "Comcast - Universal Studios", "TWDC", "TWDC", "TWDC", "Lego", "Mattel",
            "TWDC", "EA", "TWDC",
        ],
        "twdc_int": [0, 0, 1, 1, 1, 0, 0, 1, 0, 1],
        "franchise_n1_str": [
            "Marvel", "Universal Pictures", "Disney", "Disney", "Disney", "Lego Friends", "Mattel",
            "Disney", "Plants vs Zombies", "Disney",
        ],
        "franchise_n2_str": [
            "Marvel", "Mi villano favorito", "Frozen", "Los simpsons", "Los simpsons", "Lego Friends",
            "Max Steel", "Jorobado de Notre Dame", "Plants vs Zombies", "Lilo y Stitch",
        ],
        "franchise_n3_str": [None] * 10,
        "content_str": [
            "Spiderman", "Minions", "Frozen", "Los simpsons", "Los simpsons", "Lego Friends",
            "Max Steel", "Jorobado", "Plants vs Zombies", "Lilo y Stitch",
        ],
        "comment_str": [None] * 7 + ["Igor del jorobado", None, None],
    }
)


@pytest.fixture(scope="module")
def matcher():
    return build_matcher(BRANDS, CHARACTERS, ["Juegos y Juguetes", "Celulares y Smartphones"])


def match(matcher, *keywords):
    """Match keywords as one batch and return {keyword: (brands, characters)}."""
    results = matcher.match_keywords(keywords)
    out = {}
    for keyword in keywords:
        found = results[normalize_text(keyword)]
        out[keyword] = (
            [m.entity.name for m in found.brands],
            [m.entity.name for m in found.characters],
        )
    return out


def test_exact_whole_word_matches(matcher):
    result = match(matcher, "zapatillas nike", "celular samsung a54", "impresora hp")
    assert result["zapatillas nike"] == (["Nike"], [])
    assert result["celular samsung a54"] == (["Samsung"], [])
    assert result["impresora hp"] == (["HP"], [])


def test_never_matches_inside_a_word(matcher):
    # The old substring logic matched "camper" inside "campera".
    result = match(matcher, "campera de abrigo", "lilostitch")
    assert result["campera de abrigo"] == ([], [])
    assert result["lilostitch"] == ([], [])


def test_ambiguous_brand_is_never_matched(matcher):
    result = match(matcher, "power bank xiaomi", "power", "remera polo")
    assert result["power bank xiaomi"] == ([], [])
    assert result["power"] == ([], [])
    assert result["remera polo"] == ([], [])


def test_longest_alias_wins(matcher):
    assert match(matcher, "polo ralph lauren hombre")["polo ralph lauren hombre"][0] == ["Polo Ralph Lauren"]


def test_unit_after_number_is_not_a_brand(matcher):
    result = match(matcher, "motor 2 hp", "motor 1.5 hp")
    assert result["motor 2 hp"] == ([], [])
    assert result["motor 1.5 hp"] == ([], [])


def test_enye_is_preserved(matcher):
    assert match(matcher, "cañon de confeti")["cañon de confeti"] == ([], [])
    assert match(matcher, "camara canon")["camara canon"] == (["Canon"], [])


def test_compact_spelling(matcher):
    result = match(matcher, "spiderman", "spider-man", "play station 5", "playstation 5")
    assert result["spiderman"][1] == ["Spider Man"]
    assert result["spider-man"][1] == ["Spider Man"]
    assert result["play station 5"][0] == ["Playstation"]


def test_split_spelling_needs_the_joined_one_in_the_batch(matcher):
    assert match(matcher, "go pro hero 11")["go pro hero 11"][0] == []
    backed = match(matcher, "go pro hero 11", "gopro hero 12")
    assert backed["go pro hero 11"][0] == ["GoPro"]


def test_compact_never_joins_ordinary_phrases(matcher):
    result = match(matcher, "iphone 15 pro max", "promax", "el gato con botas", "elgato stream deck")
    assert result["iphone 15 pro max"] == ([], [])  # all generic words
    assert result["el gato con botas"] == ([], [])  # starts with a stopword
    assert result["elgato stream deck"][0] == ["Elgato"]


def test_ambiguity_is_shared_by_spellings(matcher):
    # "big bang" is an everyday phrase, so "bigbang" is not trusted either.
    assert match(matcher, "bigbang theory", "big bang")["bigbang theory"] == ([], [])


def test_character_plural_variant_but_not_for_brands(matcher):
    result = match(matcher, "peluche minion", "pochoclera minions", "camiseta pumas")
    assert result["peluche minion"][1] == ["Minions"]
    assert result["camiseta pumas"] == ([], [])  # "pumas" is a club, not Puma


def test_one_word_variant_needs_the_listed_form_in_the_batch(matcher):
    assert match(matcher, "peluche minion")["peluche minion"][1] == []


def test_ambiguous_character_needs_franchise_context(matcher):
    result = match(matcher, "anna frozen", "muñeca anna", "igor", "igor jorobado")
    assert result["anna frozen"][1] == ["Anna"]
    assert result["muñeca anna"][1] == []
    assert result["igor"][1] == []  # flagged by the curator comment
    assert result["igor jorobado"][1] == ["Igor"]


def test_character_typo_needs_batch_support(matcher):
    batch = ["peluche stitch", "mochila stitch", "stitch disney", "peluche stich"]
    assert match(matcher, *batch)["peluche stich"][1] == ["Stitch"]

    lonely = match(matcher, "peluche stich")  # canonical spelling absent from the batch
    assert lonely["peluche stich"][1] == []


def test_brands_are_never_typo_corrected(matcher):
    batch = ["samsung galaxy", "funda samsung", "samsung a14", "celular sansung"]
    assert match(matcher, *batch)["celular sansung"][0] == []


def test_fuzzy_never_rewrites_a_frequent_word(matcher):
    batch = ["album mundial", "figuritas mundial", "mundial 2026", "camiseta mundial", "mondial"]
    assert match(matcher, *batch)["album mundial"] == ([], [])


def test_fuzzy_never_changes_digits():
    toys = build_matcher(
        BRANDS.iloc[0:0],
        pd.DataFrame({"character_str": ["Toy Story 4"], "franchise_n1_str": ["Pixar"]}),
    )
    results = toys.match_keywords(["toy story 4", "muñeco toy story 4", "toy story 5"])
    assert results["toy story 5"].characters == ()


def test_fuzzy_never_rewrites_a_dictionary_word(matcher):
    batch = ["peluche stitch", "mochila stitch", "stitch disney", "nintendo switch"]
    assert match(matcher, *batch)["nintendo switch"] == ([], [])


def test_fuzzy_keeps_both_ends_of_the_word(matcher):
    batch = ["peluche stitch", "mochila stitch", "stitch disney", "peluche stitchy"]
    assert match(matcher, *batch)["peluche stitchy"][1] == []


def test_singular_of_a_plural_character(matcher):
    result = match(matcher, "plants vs zombies", "plants vs zombie")
    assert result["plants vs zombie"][1] == ["Plants vs Zombies"]


def test_nested_unrelated_match_is_dropped(matcher):
    result = match(matcher, "jessica simpson perfume", "remera simpson", "muñeco max steel")
    assert result["jessica simpson perfume"] == (["Jessica Simpson"], [])
    assert result["remera simpson"] == ([], ["Simpson"])
    assert result["muñeco max steel"] == ([], ["Max Steel"])


def test_nested_related_match_is_kept(matcher):
    assert match(matcher, "lego friends casa")["lego friends casa"] == (["Lego"], ["Lego Friends"])


def test_fuzzy_can_be_disabled():
    strict = build_matcher(BRANDS, CHARACTERS, config=MatchingConfig(fuzzy_enabled=False))
    results = strict.match_keywords(["peluche stitch", "mochila stitch", "peluche stich"])
    assert results["peluche stich"].characters == ()
