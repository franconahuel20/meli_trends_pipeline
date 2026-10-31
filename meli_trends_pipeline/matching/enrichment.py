"""Builds the matcher from reference tables and enriches trend rows (L2 -> L3)."""

from __future__ import annotations

import re
from dataclasses import replace
from datetime import datetime
from typing import Iterable

import pandas as pd

from .lexicon import Lexicon
from .linguistics import KeywordAnalyzer, SimpleAnalyzer, keyword_text, language_of, lemmatized, nouns
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
# Optional L2 columns: the L1 file a row came from and its 0-based row number there.
SOURCE_FILE_COLUMN = "_internal_filename_str"
SOURCE_ROW_COLUMN = "file_row_id_int"
# Same order as the business layout of the final `trends` table (week_dte is added by dbt),
# followed by the matching audit trail.
L3_COLUMNS = (
    *BASE_COLUMNS,
    SOURCE_FILE_COLUMN,
    "loading_dtm",
    SOURCE_ROW_COLUMN,
    "brand_str",
    "character_str",
    "second_brand_str",
    *CHARACTER_ATTRIBUTES,
    "keyword_in_spanish_str",
    "normalized_keyword_es_str",
    "keyword_es_without_stopwords_str",
    "character_without_stopwords_str",
    "lemmatized_keyword_str",
    "nouns_keyword_str",
    "has_franchise_n2_str",
    "has_franchise_n3_str",
    "has_character_str",
    "has_franchise_n1_str",
    "has_brand_str",
    "branded_str",
    "year_calendar_int",
    "month_calendar_int",
    "day_calendar_int",
    "brand_match_method_str",
    "brand_match_score_int",
    "brand_matched_text_str",
    "character_match_method_str",
    "character_match_score_int",
    "character_matched_text_str",
)
_WORD = re.compile(r"[^\W\d_]+(?:'[^\W\d_]+)?")


def _clean(value: object) -> object:
    if is_missing(value):
        return None
    if isinstance(value, str):
        value = " ".join(value.split())
        return value or None
    return value


def display_name(name: str) -> str:
    """Brand as shown in dashboards: an all-lowercase name gets title case ("new era" ->
    "New Era", "fisher-price" -> "Fisher-Price", "johnson's" -> "Johnson's"); a name that
    already has capitals is kept."""
    if name != name.lower():
        return name
    return _WORD.sub(lambda m: m.group(0)[0].upper() + m.group(0)[1:], name)


def build_entities(
    brands: pd.DataFrame, characters: pd.DataFrame, lexicon: Lexicon
) -> tuple[list[Entity], list[Entity]]:
    rules = lexicon.brand_rules
    # A rule redefines its alias: "wilson" from the master list (ambiguous) is replaced by
    # the rule that allows it in Deportes y Fitness only.
    ruled_aliases = {rule.tokens for rule in rules}
    rule_display = {normalize_text(rule.brand): rule.brand for rule in rules}

    brand_entities = []
    master_aliases = set()
    for entity_id, row in enumerate(brands.to_dict("records")):
        name = _clean(row.get("brand_str"))
        tokens = tokenize(name)
        master_aliases.add(tokens)
        if not tokens or tokens in ruled_aliases:
            continue
        brand_entities.append(
            Entity(
                kind=BRAND,
                entity_id=entity_id,
                name=str(name),
                tokens=tokens,
                ambiguous=lexicon.is_ambiguous_alias(tokens, BRAND),
                attributes={
                    "branded_int": row.get("branded_int"),
                    "display": rule_display.get(normalize_text(name)) or display_name(str(name)),
                    "master_list": True,
                },
            )
        )
    rule_entities = [
        Entity(
            kind=BRAND,
            entity_id=len(brands) + offset,
            name=rule.brand,
            tokens=rule.tokens,
            ambiguous=False,
            categories=rule.categories,
            attributes={
                "branded_int": 1,
                "display": rule.brand,
                "master_list": rule.tokens in master_aliases,
            },
        )
        for offset, rule in enumerate(rules)
    ]

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
        # Curated rules are never ambiguous (their category list is the guard).
        _propagate_ambiguity(brand_entities, lexicon) + rule_entities,
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


def _brand_display(match: Match) -> str:
    return str(match.entity.attributes.get("display") or match.entity.name)


def _summarize(keyword: str, matches: KeywordMatches, lexicon: Lexicon) -> tuple[dict, frozenset[str]]:
    """Enrichment columns of one (keyword, category) and the words naming a brand/character."""
    tokens = keyword.split()
    covered: set[int] = set()
    for match in (*matches.brands, *matches.characters):
        covered.update(range(match.start, match.end))

    brands: list[Match] = []
    # A brand named as such beats a product line: "notebook dell core i7" is Dell, then Intel.
    for match in sorted(matches.brands, key=lambda m: not m.entity.attributes.get("master_list")):
        # "iphone apple" names Apple once.
        if all(normalize_text(_brand_display(match)) != normalize_text(_brand_display(b)) for b in brands):
            brands.append(match)
    brand = brands[0] if brands else None
    character = matches.characters[0] if matches.characters else None
    attributes = character.entity.attributes if character else {}

    is_branded_brand = brand is not None and _to_int(brand.entity.attributes.get("branded_int")) != 0
    without_stopwords = [t for t in tokens if not lexicon.is_stopword(t)]
    character_words = [t for t in character.entity.tokens if not lexicon.is_stopword(t)] if character else []

    summary = {
        "brand_str": _brand_display(brand) if brand else None,
        "second_brand_str": _brand_display(brands[1]) if len(brands) > 1 else None,
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
        "has_brand_str": _yes_no(brand is not None),
        "has_character_str": _yes_no(character is not None),
        "has_franchise_n1_str": _yes_no(attributes.get("franchise_n1_str") is not None),
        "has_franchise_n2_str": _yes_no(attributes.get("franchise_n2_str") is not None),
        "has_franchise_n3_str": _yes_no(attributes.get("franchise_n3_str") is not None),
        "branded_str": "Branded" if is_branded_brand or character is not None else "Unbranded",
    }
    return summary, frozenset(tokens[i] for i in covered)


def enrich_trends(
    trends: pd.DataFrame,
    matcher: EntityMatcher,
    loaded_at: datetime,
    analyzer: KeywordAnalyzer | None = None,
) -> pd.DataFrame:
    """Return the L3 dataset: L2 columns plus brand/character enrichment, lemmas and flags.

    ``analyzer`` provides lemmas and parts of speech (the pipeline passes spaCy); without
    it keywords are used as they are and every content word counts as a noun.
    """
    missing = [c for c in BASE_COLUMNS if c not in trends.columns]
    if missing:
        raise ValueError(f"L2 dataset is missing columns: {missing}")
    analyzer = analyzer or SimpleAnalyzer(matcher.lexicon)

    trends = trends.reset_index(drop=True)
    df = trends.loc[:, list(BASE_COLUMNS)].copy()
    normalized = df["keyword_str"].map(normalize_text)
    categories = df["category_str"].map(normalize_text)
    pairs = list(zip(normalized, categories))
    results = matcher.match_pairs(pairs)
    empty = KeywordMatches()
    summaries = {pair: _summarize(pair[0], results.get(pair, empty), matcher.lexicon) for pair in set(pairs)}

    texts = df["keyword_str"].map(keyword_text)
    languages = df["country_str"].map(language_of)
    analyzed: list = [None] * len(df)
    for language in sorted(set(languages)):
        rows = [i for i, lang in enumerate(languages) if lang == language]
        for i, tokens in zip(rows, analyzer.analyze([texts[i] for i in rows], language)):
            analyzed[i] = tokens

    records = []
    for i, pair in enumerate(pairs):
        summary, covered = summaries[pair]
        records.append(
            {
                **summary,
                "lemmatized_keyword_str": lemmatized(analyzed[i]),
                "nouns_keyword_str": nouns(analyzed[i], covered, matcher.lexicon),
            }
        )
    enrichment = pd.DataFrame(records, index=df.index)

    out = pd.concat([df, enrichment], axis=1)
    dates = pd.to_datetime(out["date_dte"], errors="raise")
    out["date_dte"] = dates.dt.date
    out["keyword_in_spanish_str"] = out["keyword_str"]
    out["year_calendar_int"] = dates.dt.year.astype("Int64")
    out["month_calendar_int"] = dates.dt.month.astype("Int64")
    out["day_calendar_int"] = dates.dt.day.astype("Int64")
    out[SOURCE_FILE_COLUMN] = trends[SOURCE_FILE_COLUMN] if SOURCE_FILE_COLUMN in trends else None
    if SOURCE_ROW_COLUMN in trends:
        out[SOURCE_ROW_COLUMN] = pd.to_numeric(trends[SOURCE_ROW_COLUMN]).astype("Int64")
    else:
        out[SOURCE_ROW_COLUMN] = pd.array(range(len(out)), dtype="Int64")
    out["loading_dtm"] = pd.Timestamp(loaded_at)
    for column in ("brand_match_score_int", "character_match_score_int", "twdc_int"):
        out[column] = out[column].astype("Int64")
    return out.loc[:, list(L3_COLUMNS)]
