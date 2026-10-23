import math

import pandas as pd
import pytest

from meli_trends_pipeline.matching.text import has_digit, normalize_text, tokenize


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("  Zapatillas   NIKE  ", "zapatillas nike"),
        ("Pokémon", "pokemon"),
        ("Cañón de confeti", "cañon de confeti"),  # ñ is kept: "cañon" must not become "canon"
        ("MUÑECA", "muñeca"),
        ("Spider-Man", "spider man"),
        ("Levi's 501", "levis 501"),
        ("H&M", "hm"),
        ("Disney+", "disney"),
        ("Black+Decker", "black decker"),
        ("R2-D2", "r2 d2"),
        ("Coração", "coracao"),
        ("dr. martens / botas", "dr martens botas"),
        ("", ""),
    ],
)
def test_normalize_text(raw, expected):
    assert normalize_text(raw) == expected


@pytest.mark.parametrize("missing", [None, float("nan"), pd.NA, math.nan])
def test_normalize_text_missing_values(missing):
    assert normalize_text(missing) == ""


def test_tokenize_and_digits():
    assert tokenize("Smart TV 50''") == ("smart", "tv", "50")
    assert has_digit("ps5") and not has_digit("samsung")
