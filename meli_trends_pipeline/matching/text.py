"""Text normalization shared by reference names and trend keywords.

Both sides of every comparison go through :func:`normalize_text`, so matching
rules only ever deal with lowercase ASCII tokens (plus ``ñ``).
"""

from __future__ import annotations

import re
import unicodedata
from typing import Any

import pandas as pd
from unidecode import unidecode

# "ñ" is kept on purpose: folding it to "n" creates false matches such as
# "cañon" (cannon) -> "canon" (the camera brand) or "moño" -> "mono".
_ENYE_PLACEHOLDER = "\u0001"
# Characters that glue a name together rather than separate words:
# "levi's" -> "levis", "h&m" -> "hm". Anything else ("-", "+", "/", ".") separates.
_JOINERS = re.compile(r"['’`´&]")
_SEPARATORS = re.compile(r"[^0-9a-zñ]+")
_DIGIT = re.compile(r"\d")


def is_missing(value: Any) -> bool:
    """True for None, NaN, pd.NA and other pandas missing markers."""
    if value is None:
        return True
    try:
        return bool(pd.isna(value))
    except (TypeError, ValueError):
        # pd.isna on list-likes returns an array; those are never "missing" scalars.
        return False


def normalize_text(value: Any) -> str:
    """Lowercase, strip accents (except ñ), drop punctuation and collapse spaces."""
    if is_missing(value):
        return ""
    text = unicodedata.normalize("NFC", str(value)).lower()
    text = text.replace("ñ", _ENYE_PLACEHOLDER)
    text = unidecode(text).replace(_ENYE_PLACEHOLDER, "ñ")
    text = _JOINERS.sub("", text)
    text = _SEPARATORS.sub(" ", text)
    return " ".join(text.split())


def tokenize(value: Any) -> tuple[str, ...]:
    return tuple(normalize_text(value).split())


def has_digit(token: str) -> bool:
    return bool(_DIGIT.search(token))
