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
    ("impresora hp", "HP", None),  # display rule of the master-list "hp"
    ("cable rca", None, None),  # connector type, not the RCA brand
    ("luces rgb", None, None),
    ("ps4 slim", "Playstation", None),  # product line; old logic returned the brand "slim"
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
    ("iphone 15 pro max", "Apple", None),  # product line, not the brand "promax"
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


# Brand rules that depend on the category of the keyword (wordlists/brand_rules.txt).
CATEGORY_CASES = [
    # keyword, category, expected brand
    ("raqueta wilson pro staff", "Deportes y Fitness", "Wilson"),
    ("separadores wilson jones", "Arte, Librería y Mercería", None),
    ("amplificador marshall", "Instrumentos Musicales", "Marshall"),
    ("boss katana 50", "Instrumentos Musicales", "Boss"),
    ("leche nido 3", "Bebés", "Nido"),
    ("leche nan supreme 2", "Bebés", "NAN"),
    ("memoria ram ddr4", "Computación", None),
    ("camioneta ram 1000", "Autos, Motos y Otros", "RAM"),
    ("arena para gato", "Animales y Mascotas", None),
    ("antiparras arena", "Deportes y Fitness", "Arena"),
    ("corona de adviento", "Souvenirs, Cotillón y Fiestas", None),
    ("cerveza corona", "Alimentos y Bebidas", "Corona"),
    ("switch usb", "Computación", None),
    ("joystick switch", "Consolas y Videojuegos", "Nintendo"),
    ("galaxy s24 ultra", "Celulares y Teléfonos", "Samsung"),
    ("proyector galaxy", "Hogar, Muebles y Jardín", None),
    ("maquillaje mac", "Belleza y Cuidado Personal", "MAC Cosmetics"),
    ("mac mini m4", "Computación", "Apple"),
    ("gorra new era yankees", "Deportes y Fitness", "New Era"),
    ("campera columbia mujer", "Ropa y Accesorios", "Columbia"),
    ("chromecast 4k", "Electrónica, Audio y Video", "Google"),
    ("ryzen 5 5600g", "Computación", "AMD"),
    ("rtx 4060", "Computación", "Nvidia"),
    ("meta quest 3", "Consolas y Videojuegos", "Meta"),
    ("talco johnson baby", "Bebés", "Johnson's"),
]


@pytest.fixture(scope="module")
def category_results(real_matcher):
    return real_matcher.match_pairs([(k, c) for k, c, _ in CATEGORY_CASES])


@pytest.mark.parametrize("keyword, category, brand", CATEGORY_CASES, ids=[c[0] for c in CATEGORY_CASES])
def test_category_brand_rules(category_results, keyword, category, brand):
    found = category_results[(normalize_text(keyword), normalize_text(category))]
    assert (found.brands[0].entity.name if found.brands else None) == brand


def test_brand_plurals_on_real_data(real_matcher):
    results = real_matcher.match_keywords(
        ["legos usados", "lego city", "googles natacion", "google pixel", "toppers para torta", "topper"]
    )
    assert [m.entity.name for m in results["legos usados"].brands] == ["lego"]
    assert results["googles natacion"].brands == ()  # swimming goggles
    assert results["toppers para torta"].brands == ()  # cake toppers


def test_brand_rules_parse_and_use_known_categories(real_matcher, reference_frames):
    subcat = reference_frames["mercado_libre_subcat"]
    known = {normalize_text(c) for c in subcat["homologated_category_str"].dropna()}
    rules = real_matcher.lexicon.brand_rules
    assert len(rules) > 100
    for rule in rules:
        assert rule.categories is None or rule.categories <= known, rule

