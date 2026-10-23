"""Precision regression suite against the real reference files in data/input.

Each case was a false positive (or a miss) of the previous Airflow implementation,
which used substring search plus thefuzz token_set_ratio >= 85/90.
"""

import pytest

from meli_trends_pipeline.matching import normalize_text

# A realistic batch: the fuzzy step only fixes typos whose correct spelling is frequent.
BACKGROUND = [
    "samsung galaxy a15",
    "funda samsung a54",
    "samsung s24 ultra",
    "album mundial 2026",
    "figuritas mundial",
    "camiseta mundial",
    "peluche stitch",
    "mochila stitch",
    "stitch disney",
    "auto rayo mcqueen",
    "rayo mcqueen grande",
    "gopro hero 12",
    "pochoclera minions",
]

CASES = [
    # keyword, expected brand, expected character
    ("zapatillas nike", "nike", None),
    ("celular sansung a54", None, None),  # brands are never typo-corrected
    ("peluche stich", None, "Stitch"),  # character typo, "stitch" is frequent in the batch
    ("rayo macqueen", None, "Rayo McQueen"),
    ("album mundial", None, None),  # never "mondial"
    ("power bank xiaomi", "xiaomi", None),  # "power" / "power bank" are not brands here
    ("motor 2 hp", None, None),  # horsepower, not HP
    ("impresora hp", "hp", None),
    ("cable rca", None, None),  # connector type, not the RCA brand
    ("luces rgb", None, None),
    ("ps4 slim", None, None),  # old logic returned the brand "slim"
    ("remera polo", None, None),
    ("polo ralph lauren", "polo ralph lauren", None),
    ("botas cat", None, None),
    ("cat chow", "Cat Chow", None),
    ("juego de mesa uno", None, None),
    ("vr box", None, None),
    ("de fabrica", None, None),
    ("ariel liquido", None, None),  # detergent, not the mermaid
    ("ariel la sirenita", None, "Ariel La Sirenita"),
    ("campera", None, None),  # old logic: brand "camper"
    ("camper fisher price", "fisher-price", None),  # a toy camper, not the shoe brand
    ("zapatillas topper mujer", "topper", None),
    ("termo stanley", "stanley", None),  # old logic: character "stan"
    ("jessica simpson perfume", "jessica simpson", None),  # old logic: character "simpson"
    ("remera simpson", None, "Simpson"),
    ("lisa simpsons", None, "Lisa Simpsons"),
    ("remera lisa", None, None),
    ("anna frozen", None, "Anna"),
    ("muñeca anna", None, None),
    ("dinosaurio t rex", None, None),  # old logic: brand "rex", character "t rex"
    ("cañon de confeti", None, None),
    ("camara canon", "canon", None),
    ("spiderman", None, "Spiderman"),
    ("muñeco spider-man", None, "Spider man"),
    ("lego friends", "lego", "Lego Friends"),
    ("hot wheels", "hot wheels", "Hot Wheels"),
    ("peluche stitch", None, "Stitch"),
    ("minion", None, "Minions"),
    ("camiseta pumas", None, None),
    ("puma suede", "puma", None),
    ("the north face campera", "the north face", None),
    ("camiseta river plate", "river plate", None),
    ("taza harry potter", None, "Harry Potter"),
    ("bolt disney", None, "Bolt Disney"),
    # False positives found on the first real run (2026-10-22) of the new pipeline:
    ("saxo tenor yamaha", "yamaha", None),  # "saxo" is the instrument
    ("iphone 15 pro max", None, None),  # not the brand "promax"
    ("jeans hip hop", None, None),
    ("el gato con botas dvd", None, None),  # not Elgato
    ("oculos do minion", None, "Minions"),  # not the brand "dominion"
    ("raquetas tecnifibre importador directo", None, None),  # not DirecTV
    ("turbo racing drift", None, None),
    ("bee venom", None, None),
    ("patins roller", None, None),
    ("needoh cube", None, None),
    ("tupper para leche en polvo", None, None),  # not Topper
    ("ayn thor", None, "Thor"),  # the character stays; the unrelated brand "thor" does not
    ("doom eternal switch", None, None),  # "eternal" is a word, not the Eternals
    ("hollyland lark m2", "hollyland", None),
    ("go pro hero 11", "gopro", None),  # split spelling backed by "gopro" in the batch
    ("taladro black+decker", "black+decker", None),
]


@pytest.fixture(scope="module")
def batch_results(real_matcher):
    return real_matcher.match_keywords([*BACKGROUND, *(c[0] for c in CASES)])


@pytest.mark.parametrize("keyword, brand, character", CASES, ids=[c[0] for c in CASES])
def test_reference_matching(batch_results, keyword, brand, character):
    found = batch_results[normalize_text(keyword)]
    assert (found.brands[0].entity.name if found.brands else None) == brand
    assert (found.characters[0].entity.name if found.characters else None) == character


def test_every_trusted_name_exists_in_the_reference_data(real_matcher, reference_frames):
    brands = {normalize_text(n) for n in reference_frames["brands"]["brand_str"]}
    characters = {normalize_text(n) for n in reference_frames["characters"]["character_str"]}
    assert real_matcher.lexicon.trusted_brands <= brands
    assert real_matcher.lexicon.trusted_characters <= characters
