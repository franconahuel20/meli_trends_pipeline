"""Builds the matcher from reference tables and enriches trend rows (L2 -> L3)."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime
from typing import Iterable

import pandas as pd

from .lexicon import Lexicon
from .matcher import (
    BRAND,
    CHARACTER,
    Entity,
    EntityMatcher,
    KeywordMatches,
    Match,
    MatchingConfig,
    plural_variants,
)
from .text import is_missing, normalize_text, tokenize

CHARACTER_ATTRIBUTES = (
    "group_company_owner_rights_str",
    "twdc_int",
    "franchise_n1_str",
    "franchise_n2_str",
    "franchise_n3_str",
    "content_str",
)
_CONTEXT_SOURCES = (
    "franchise_n1_str",
    "franchise_n2_str",
    "franchise_n3_str",
    "content_str",
    "group_company_owner_rights_str",
)

BASE_COLUMNS = (
    "keyword_str",
    "url_str",
    "date_dte",
    "country_str",
    "category_str",
    "subcategory_str",
)
L3_COLUMNS = (
    *BASE_COLUMNS,
    "brand_str",
    "second_brand_str",
    "brand_match_method_str",
    "brand_match_score_int",
    "brand_matched_text_str",
    "character_str",
    "character_match_method_str",
    "character_match_score_int",
    "character_matched_text_str",
    *CHARACTER_ATTRIBUTES,
    "keyword_in_spanish_str",
    "normalized_keyword_es_str",
    "keyword_es_without_stopwords_str",
    "character_without_stopwords_str",
    "nouns_keyword_str",
    "has_brand_str",
    "has_character_str",
    "has_franchise_n1_str",
    "has_franchise_n2_str",
    "has_franchise_n3_str",
    "branded_str",
    "year_calendar_int",
    "month_calendar_int",
    "day_calendar_int",
    "file_row_id_int",
    "loading_dtm",
)


def _clean(value: object) -> object:
    if is_missing(value):
        return None
    if isinstance(value, str):
        value = " ".join(value.split())
        return value or None
    return value


def build_entities(
    brands: pd.DataFrame, characters: pd.DataFrame, lexicon: Lexicon
) -> tuple[list[Entity], list[Entity]]:
    brand_entities = []
    for entity_id, row in enumerate(brands.to_dict("records")):
        name = _clean(row.get("brand_str"))
        tokens = tokenize(name)
        if not tokens:
            continue
        brand_entities.append(
            Entity(
                kind=BRAND,
                entity_id=entity_id,
                name=str(name),
                tokens=tokens,
                ambiguous=lexicon.is_ambiguous_alias(tokens, BRAND),
                attributes={"branded_int": row.get("branded_int")},
            )
        )

    character_entities = []
    for entity_id, row in enumerate(characters.to_dict("records")):
        name = _clean(row.get("character_str"))
        tokens = tokenize(name)
        if not tokens:
            continue
        related = set()
        for column in _CONTEXT_SOURCES:
            for token in tokenize(row.get(column)):
                if lexicon.is_context_term(token):
                    related.add(token)
                    related.update(v for v in plural_variants(token) if lexicon.is_context_term(v))
        # A curator comment flags a name that collides with something else
        # ("Igor del jorobado"). Multi-word names already carry their qualifier
        # ("Bolt Disney"), so only one-word names need extra context.
        flagged = len(tokens) == 1 and _clean(row.get("comment_str")) is not None
        character_entities.append(
            Entity(
                kind=CHARACTER,
                entity_id=entity_id,
                name=str(name),
                tokens=tokens,
                ambiguous=(flagged and not lexicon.is_trusted(tokens, CHARACTER))
                or lexicon.is_ambiguous_alias(tokens, CHARACTER),
                context=frozenset(related - set(tokens)),
                related_terms=frozenset(related),
                attributes={c: _clean(row.get(c)) for c in CHARACTER_ATTRIBUTES},
            )
        )
    return (
        _propagate_ambiguity(brand_entities, lexicon),
        _propagate_ambiguity(character_entities, lexicon),
    )


def _propagate_ambiguity(entities: list[Entity], lexicon: Lexicon) -> list[Entity]:
    """Spellings that differ only in spacing share ambiguity: "bigbang" follows "big bang"."""
    ambiguous = {e.compact for e in entities if e.ambiguous}
    return [
        replace(e, ambiguous=True)
        if not e.ambiguous and e.compact in ambiguous and not lexicon.is_trusted(e.tokens, e.kind)
        else e
        for e in entities
    ]


def build_matcher(
    brands: pd.DataFrame,
    characters: pd.DataFrame,
    category_terms: Iterable[str] = (),
    lexicon: Lexicon | None = None,
    config: MatchingConfig | None = None,
) -> EntityMatcher:
    """``category_terms`` (category/subcategory names) are treated as generic vocabulary."""
    lexicon = (lexicon or Lexicon.load()).with_generic_terms(category_terms)
    brand_entities, character_entities = build_entities(brands, characters, lexicon)
    return EntityMatcher(brand_entities, character_entities, lexicon, config)


def _yes_no(flag: bool) -> str:
    return "YES" if flag else "NO"


def _to_int(value: object) -> int | None:
    number = pd.to_numeric(value, errors="coerce")
    return None if is_missing(number) else int(number)


def _summarize(keyword: str, matches: KeywordMatches, lexicon: Lexicon) -> dict:
    tokens = keyword.split()
    covered: set[int] = set()
    for match in (*matches.brands, *matches.characters):
        covered.update(range(match.start, match.end))

    brands: list[Match] = []
    for match in matches.brands:
        if all(match.entity.name != b.entity.name for b in brands):
            brands.append(match)
    brand = brands[0] if brands else None
    character = matches.characters[0] if matches.characters else None
    attributes = character.entity.attributes if character else {}

    is_branded_brand = brand is not None and _to_int(brand.entity.attributes.get("branded_int")) != 0
    without_stopwords = [t for t in tokens if not lexicon.is_stopword(t)]
    nouns = [
        t
        for i, t in enumerate(tokens)
        if i not in covered and not lexicon.is_stopword(t) and not t.isdigit()
    ]
    character_words = [t for t in character.entity.tokens if not lexicon.is_stopword(t)] if character else []

    return {
        "brand_str": brand.entity.name if brand else None,
        "second_brand_str": brands[1].entity.name if len(brands) > 1 else None,
        "brand_match_method_str": brand.method if brand else None,
        "brand_match_score_int": brand.score if brand else None,
        "brand_matched_text_str": brand.text if brand else None,
        "character_str": character.entity.name if character else None,
        "character_match_method_str": character.method if character else None,
        "character_match_score_int": character.score if character else None,
        "character_matched_text_str": character.text if character else None,
        "group_company_owner_rights_str": attributes.get("group_company_owner_rights_str"),
        "twdc_int": 1 if character and _to_int(attributes.get("twdc_int")) == 1 else 0,
        "franchise_n1_str": attributes.get("franchise_n1_str"),
        "franchise_n2_str": attributes.get("franchise_n2_str"),
        "franchise_n3_str": attributes.get("franchise_n3_str"),
        "content_str": attributes.get("content_str"),
        "normalized_keyword_es_str": keyword or None,
        "keyword_es_without_stopwords_str": " ".join(without_stopwords) or None,
        "character_without_stopwords_str": " ".join(character_words) or None,
        "nouns_keyword_str": " ".join(nouns) or None,
        "has_brand_str": _yes_no(brand is not None),
        "has_character_str": _yes_no(character is not None),
        "has_franchise_n1_str": _yes_no(attributes.get("franchise_n1_str") is not None),
        "has_franchise_n2_str": _yes_no(attributes.get("franchise_n2_str") is not None),
        "has_franchise_n3_str": _yes_no(attributes.get("franchise_n3_str") is not None),
        "branded_str": "Branded" if is_branded_brand or character is not None else "Unbranded",
    }


def enrich_trends(trends: pd.DataFrame, matcher: EntityMatcher, loaded_at: datetime) -> pd.DataFrame:
    """Return the L3 dataset: L2 columns plus brand/character enrichment and flags."""
    missing = [c for c in BASE_COLUMNS if c not in trends.columns]
    if missing:
        raise ValueError(f"L2 dataset is missing columns: {missing}")

    df = trends.loc[:, list(BASE_COLUMNS)].reset_index(drop=True)
    normalized = df["keyword_str"].map(normalize_text)
    results = matcher.match_keywords(normalized.unique())
    empty = KeywordMatches()
    summaries = {
        keyword: _summarize(keyword, results.get(keyword, empty), matcher.lexicon)
        for keyword in normalized.unique()
    }
    enrichment = pd.DataFrame([summaries[k] for k in normalized], index=df.index)

    out = pd.concat([df, enrichment], axis=1)
    dates = pd.to_datetime(out["date_dte"], errors="raise")
    out["date_dte"] = dates.dt.date
    out["keyword_in_spanish_str"] = out["keyword_str"]
    out["year_calendar_int"] = dates.dt.year.astype("Int64")
    out["month_calendar_int"] = dates.dt.month.astype("Int64")
    out["day_calendar_int"] = dates.dt.day.astype("Int64")
    out["file_row_id_int"] = pd.array(range(1, len(out) + 1), dtype="Int64")
    out["loading_dtm"] = pd.Timestamp(loaded_at)
    for column in ("brand_match_score_int", "character_match_score_int", "twdc_int"):
        out[column] = out[column].astype("Int64")
    return out.loc[:, list(L3_COLUMNS)]
