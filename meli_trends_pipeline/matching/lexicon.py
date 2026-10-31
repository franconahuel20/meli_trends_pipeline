"""Word lists that drive the ambiguity rules of the matcher.

The lists live as plain text files in ``matching/wordlists/`` so they can be
reviewed and tuned without touching code.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from importlib import resources
from typing import Iterable

from .text import has_digit, normalize_text

_WORDLISTS_PACKAGE = "meli_trends_pipeline.matching.wordlists"
# In a brand rule alias, stands for one model code: a token with a digit ("s24", "a55", "4").
MODEL_WILDCARD = "#"


def _read_lines(file_name: str) -> list[str]:
    content = resources.files(_WORDLISTS_PACKAGE).joinpath(file_name).read_text(encoding="utf-8")
    lines = (line.strip() for line in content.splitlines())
    return [line for line in lines if line and not line.startswith("#")]


def _read_terms(file_name: str) -> frozenset[str]:
    return frozenset(term for term in map(normalize_text, _read_lines(file_name)) if term)


@dataclass(frozen=True)
class BrandRule:
    """An extra way of naming a brand: a product line ("iphone" -> Apple), a spelling the
    master list lacks ("victoria secret") or a brand that is only safe in some categories
    ("wilson" in Deportes y Fitness)."""

    tokens: tuple[str, ...]
    brand: str
    # Normalized category names; None means every category.
    categories: frozenset[str] | None = None


def _alias_tokens(alias: str) -> tuple[str, ...]:
    return tuple(
        MODEL_WILDCARD if part == MODEL_WILDCARD else token
        for part in alias.split()
        for token in ((part,) if part == MODEL_WILDCARD else normalize_text(part).split())
    )


def parse_brand_rule(line: str) -> BrandRule:
    """Parse ``alias | Brand | Category; Category`` (the categories part is optional)."""
    parts = [p.strip() for p in line.split("|")]
    if len(parts) not in (2, 3) or not parts[0] or not parts[1]:
        raise ValueError(f"Invalid brand rule {line!r}: expected 'alias | Brand [| categories]'")
    tokens = _alias_tokens(parts[0])
    if not tokens or tokens[0] == MODEL_WILDCARD:
        raise ValueError(f"Invalid brand rule {line!r}: the alias must start with a word")
    categories = None
    if len(parts) == 3 and parts[2]:
        categories = frozenset(normalize_text(c) for c in parts[2].split(";") if normalize_text(c))
    return BrandRule(tokens=tokens, brand=parts[1], categories=categories)


def _read_brand_rules(file_name: str) -> tuple[BrandRule, ...]:
    return tuple(parse_brand_rule(line) for line in _read_lines(file_name))


@dataclass(frozen=True)
class Lexicon:
    stopwords: frozenset[str]
    generic_terms: frozenset[str]
    units: frozenset[str]
    ambiguous_aliases: frozenset[str]
    trusted_brands: frozenset[str]
    trusted_characters: frozenset[str]
    # Real words that must never be typo-corrected into a character name.
    fuzzy_protected: frozenset[str] = frozenset()
    brand_rules: tuple[BrandRule, ...] = ()

    @classmethod
    def load(cls) -> "Lexicon":
        return cls(
            stopwords=_read_terms("stopwords.txt"),
            generic_terms=_read_terms("generic_terms.txt"),
            units=_read_terms("units.txt"),
            ambiguous_aliases=_read_terms("ambiguous_aliases.txt"),
            trusted_brands=_read_terms("trusted_brands.txt"),
            trusted_characters=_read_terms("trusted_characters.txt"),
            fuzzy_protected=_read_terms("fuzzy_protected_words.txt"),
            brand_rules=_read_brand_rules("brand_rules.txt"),
        )

    def with_generic_terms(self, terms: Iterable[str]) -> "Lexicon":
        """Return a copy that also treats the tokens of ``terms`` as generic vocabulary."""
        extra = {token for term in terms for token in normalize_text(term).split()}
        extra -= self.trusted_brands | self.trusted_characters
        return replace(self, generic_terms=self.generic_terms | extra)

    def is_stopword(self, token: str) -> bool:
        return token in self.stopwords

    def is_vocabulary(self, token: str) -> bool:
        """Stopwords, product vocabulary, units and numbers (``is_generic`` minus short tokens)."""
        return (
            token in self.stopwords
            or token in self.generic_terms
            or token in self.units
            or token.isdigit()
        )

    def is_generic(self, token: str) -> bool:
        """Stopwords, product vocabulary, units, numbers and one/two-letter tokens."""
        return self.is_vocabulary(token) or len(token) <= 2

    def is_context_term(self, token: str) -> bool:
        """Whether a franchise/owner token is specific enough to disambiguate a character."""
        return len(token) >= 3 and not has_digit(token) and not self.is_generic(token)

    def is_trusted(self, tokens: tuple[str, ...], kind: str) -> bool:
        trusted = self.trusted_brands if kind == "brand" else self.trusted_characters
        return " ".join(tokens) in trusted

    def is_ambiguous_alias(self, tokens: tuple[str, ...], kind: str) -> bool:
        alias = " ".join(tokens)
        if not alias:
            return True
        if self.is_trusted(tokens, kind):
            return False
        if alias in self.ambiguous_aliases:
            return True
        if len(tokens) == 1:
            # Product words, numbers and one/two-letter codes ("lg" must be trusted explicitly).
            return self.is_generic(tokens[0])
        # Phrases made only of product words ("smart tv") or letter pairs ("b w").
        return len("".join(tokens)) <= 3 or all(self.is_vocabulary(t) for t in tokens)
