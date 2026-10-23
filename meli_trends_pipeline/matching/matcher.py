"""Precision-first matching of trend keywords against brands and characters.

Matching works on normalized token sequences (see :mod:`.text`) and only ever
links whole tokens, so a reference name can never fire *inside* a word ("luca"
never matches "lucas", "belle" never matches "belleza"). Candidates come from
four increasingly permissive methods, each fenced by guards aimed at a source
of false positives observed on real Mercado Libre trends:

* ``exact``: the alias tokens appear contiguously in the keyword.
* ``compact``: same letters, different spacing ("spiderman" / "spider man",
  "hotwheels" / "hot wheels"). A split spelling ("go pro" for "gopro") only
  counts when the joined one also appears in the batch, so ordinary phrases
  ("pro max", "hip hop", "el gato") never collapse into a brand.
* ``variant``: singular/plural of a character name ("minion" / "minions");
  for one-word names the listed form must also appear in the batch. Brands get
  no variants: "pumas" is a football club, not Puma.
* ``fuzzy``: a one-letter typo of a long character name ("stich" -> Stitch),
  keeping the first and last letters, and only when the batch shows the
  correct spelling is the common one. Brands are never typo-corrected: the
  brand list is so large that a near miss is usually another real word
  ("directo" is not DirecTV, "realce" is not Realme).

Aliases that are also everyday words ("power", "polo", "anna") are ambiguous:
an ambiguous brand never matches, and an ambiguous character needs a term of
its franchise or owner elsewhere in the keyword ("anna frozen").
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Iterable, Mapping, Sequence

from rapidfuzz import fuzz, process
from rapidfuzz.distance import Levenshtein

from .lexicon import Lexicon
from .text import has_digit, normalize_text

BRAND = "brand"
CHARACTER = "character"

EXACT = "exact"
COMPACT = "compact"
VARIANT = "variant"
FUZZY = "fuzzy"
_METHOD_RANK = {EXACT: 0, COMPACT: 1, VARIANT: 2, FUZZY: 3}


@dataclass(frozen=True)
class MatchingConfig:
    fuzzy_enabled: bool = True
    # Kinds that get typo correction (see module docstring for why brands do not).
    fuzzy_kinds: tuple[str, ...] = (CHARACTER,)
    # Aliases shorter than this (letters, spaces removed) are never fuzzy matched.
    fuzzy_min_length: int = 6
    # From this length on a two-letter typo is tolerated (still one per word).
    fuzzy_two_edit_length: int = 12
    # The canonical spelling must appear in at least this many distinct keywords
    # of the batch, and this many times more often than the misspelling.
    fuzzy_min_support: int = 2
    fuzzy_support_ratio: float = 2.0
    compact_min_length: int = 5
    variant_min_length: int = 4
    max_window_tokens: int = 4


@dataclass(frozen=True, eq=False)
class Entity:
    kind: str
    entity_id: int
    name: str
    tokens: tuple[str, ...]
    ambiguous: bool
    # Terms that disambiguate an ambiguous alias (franchise/owner words).
    context: frozenset[str] = frozenset()
    # Franchise/owner words; used to decide whether overlapping brand and
    # character matches belong together ("lego" + "lego friends").
    related_terms: frozenset[str] = frozenset()
    attributes: Mapping[str, object] = field(default_factory=dict)

    @property
    def alias(self) -> str:
        return " ".join(self.tokens)

    @property
    def compact(self) -> str:
        return "".join(self.tokens)


@dataclass(frozen=True)
class Match:
    entity: Entity
    start: int
    end: int
    method: str
    score: int
    text: str

    @property
    def length(self) -> int:
        return self.end - self.start

    def overlaps(self, other: "Match") -> bool:
        return self.start < other.end and other.start < self.end

    def strictly_contains(self, other: "Match") -> bool:
        return self.start <= other.start and other.end <= self.end and self.length > other.length


@dataclass(frozen=True)
class KeywordMatches:
    brands: tuple[Match, ...] = ()
    characters: tuple[Match, ...] = ()


class NgramSupport:
    """Number of distinct keywords of a batch that contain each n-gram."""

    def __init__(self, keywords: Iterable[Sequence[str]], max_n: int) -> None:
        counts: Counter[tuple[str, ...]] = Counter()
        for tokens in keywords:
            ngrams = {
                tuple(tokens[i : i + n])
                for n in range(1, max_n + 1)
                for i in range(len(tokens) - n + 1)
            }
            counts.update(ngrams)
        self._counts = counts

    def __call__(self, ngram: Sequence[str]) -> int:
        return self._counts.get(tuple(ngram), 0)


def plural_variants(token: str) -> set[str]:
    variants = set()
    if token.endswith("s") and len(token) > 4:
        variants.add(token[:-1])
        if token.endswith("es") and len(token) > 5:
            variants.add(token[:-2])
    elif not token.endswith("s"):
        variants.add(token + "s")
        if token[-1] not in "aeiouy":
            variants.add(token + "es")
    return variants


class _KindIndex:
    """Lookup structures for one kind of entity (brands or characters)."""

    def __init__(
        self,
        kind: str,
        entities: Sequence[Entity],
        lexicon: Lexicon,
        config: MatchingConfig,
        reserved: frozenset[tuple[str, ...]],
    ) -> None:
        self.lexicon = lexicon
        self.config = config
        self.reserved = reserved
        self.exact: dict[tuple[str, ...], list[Entity]] = defaultdict(list)
        self.compact: dict[str, list[Entity]] = defaultdict(list)
        self.variant: dict[tuple[str, ...], list[Entity]] = defaultdict(list)
        fuzzy: dict[tuple[int, str], list[Entity]] = defaultdict(list)
        typo_correction = config.fuzzy_enabled and kind in config.fuzzy_kinds

        for entity in entities:
            self.exact[entity.tokens].append(entity)
            compact = entity.compact
            if len(compact) >= config.compact_min_length and not compact.isdigit():
                self.compact[compact].append(entity)
            if kind == CHARACTER:
                for variant in self._variants(entity):
                    self.variant[variant].append(entity)
            if typo_correction and not entity.ambiguous and len(compact) >= config.fuzzy_min_length:
                fuzzy[(len(entity.tokens), entity.tokens[0][0])].append(entity)

        self.max_tokens = max((len(e.tokens) for e in entities), default=0)
        self.fuzzy_buckets = {
            key: (group, [e.compact for e in group]) for key, group in fuzzy.items()
        }

    def _variants(self, entity: Entity) -> list[tuple[str, ...]]:
        last = entity.tokens[-1]
        if len(last) < self.config.variant_min_length or has_digit(last):
            return []
        out = []
        for token in sorted(plural_variants(last)):
            tokens = entity.tokens[:-1] + (token,)
            if tokens in self.reserved or self.lexicon.is_generic(token):
                continue
            out.append(tokens)
        return out

    def _compact_ok(
        self, entity: Entity, window: tuple[str, ...], support: NgramSupport | None
    ) -> bool:
        if self.lexicon.is_stopword(window[0]) or self.lexicon.is_stopword(window[-1]):
            return False  # "el gato" -> "elgato", "agua de mar" -> "demar"
        if all(self.lexicon.is_vocabulary(t) for t in window):
            return False  # "pro max" -> "promax", "smart tv" -> "smarttv"
        if len(window) > len(entity.tokens):
            # A split spelling must be backed by the joined one in the same batch.
            return support is not None and support(entity.tokens) > 0
        return True

    def candidates(
        self,
        tokens: tuple[str, ...],
        support: NgramSupport | None,
        fuzzy_cache: dict | None,
    ) -> list[Match]:
        found: list[Match] = []
        n = len(tokens)
        for start in range(n):
            for size in range(1, min(self.max_tokens, n - start) + 1):
                key = tokens[start : start + size]
                text = " ".join(key)
                for entity in self.exact.get(key, ()):
                    found.append(Match(entity, start, start + size, EXACT, 100, text))
                for entity in self.variant.get(key, ()):
                    # One-word names: the form in the reference list must also be in use
                    # in the batch ("eternal" alone is a word, not the Eternals).
                    if len(entity.tokens) > 1 or (support is not None and support(entity.tokens) > 0):
                        found.append(Match(entity, start, start + size, VARIANT, 95, text))

            for size in range(1, min(self.config.max_window_tokens, n - start) + 1):
                window = tokens[start : start + size]
                compact = "".join(window)
                if len(compact) >= self.config.compact_min_length:
                    for entity in self.compact.get(compact, ()):
                        if entity.tokens != window and self._compact_ok(entity, window, support):
                            found.append(
                                Match(entity, start, start + size, COMPACT, 100, " ".join(window))
                            )
                if support is not None and self.fuzzy_buckets:
                    if fuzzy_cache is not None and window in fuzzy_cache:
                        hits = fuzzy_cache[window]
                    else:
                        hits = self._fuzzy_hits(window, support)
                        if fuzzy_cache is not None:
                            fuzzy_cache[window] = hits
                    for entity, score in hits:
                        found.append(
                            Match(entity, start, start + size, FUZZY, score, " ".join(window))
                        )
        return found

    def _edit_budget(self, entity: Entity) -> int:
        return 2 if len(entity.compact) >= self.config.fuzzy_two_edit_length else 1

    def _tokens_close(self, alias: tuple[str, ...], window: tuple[str, ...]) -> bool:
        edits = 0
        for expected, seen in zip(alias, window):
            if expected == seen:
                continue
            if has_digit(expected) or has_digit(seen):
                return False  # "ps4" vs "ps5", "iphone 13" vs "iphone 12"
            if len(expected) <= 3 or len(seen) <= 3:
                return False
            # A typo keeps both ends; prefix/suffix changes are usually other
            # words ("toppers", "matte" vs "mattel").
            if expected[0] != seen[0] or expected[-1] != seen[-1]:
                return False
            if self.lexicon.is_generic(seen) or seen in self.lexicon.fuzzy_protected:
                return False  # a real word ("switch" is not a typo of "stitch")
            distance = Levenshtein.distance(expected, seen, score_cutoff=1)
            if distance > 1:
                return False
            edits += distance
        return edits > 0

    def _fuzzy_hits(
        self, window: tuple[str, ...], support: NgramSupport
    ) -> list[tuple[Entity, int]]:
        if window in self.reserved:
            return []  # the window is itself a reference name; exact matching owns it
        bucket = self.fuzzy_buckets.get((len(window), window[0][0]))
        if bucket is None:
            return []
        entities, compacts = bucket
        compact = "".join(window)
        if len(compact) < self.config.fuzzy_min_length - 1:
            return []
        hits = []
        window_support = max(support(window), 1)
        for _, distance, index in process.extract(
            compact, compacts, scorer=Levenshtein.distance, score_cutoff=2, limit=None
        ):
            entity = entities[index]
            if distance == 0 or distance > self._edit_budget(entity):
                continue
            if not self._tokens_close(entity.tokens, window):
                continue
            alias_support = support(entity.tokens)
            if alias_support < self.config.fuzzy_min_support:
                continue
            if alias_support < self.config.fuzzy_support_ratio * window_support:
                continue
            hits.append((entity, int(round(fuzz.ratio(compact, entity.compact)))))
        return hits


class EntityMatcher:
    """Finds brand and character mentions in normalized keyword tokens."""

    def __init__(
        self,
        brands: Sequence[Entity],
        characters: Sequence[Entity],
        lexicon: Lexicon,
        config: MatchingConfig | None = None,
    ) -> None:
        self.lexicon = lexicon
        self.config = config or MatchingConfig()
        reserved = frozenset(e.tokens for e in (*brands, *characters))
        self._brands = _KindIndex(BRAND, brands, lexicon, self.config, reserved)
        self._characters = _KindIndex(CHARACTER, characters, lexicon, self.config, reserved)

    def match_tokens(
        self,
        tokens: Sequence[str],
        support: NgramSupport | None = None,
        fuzzy_cache: dict | None = None,
    ) -> KeywordMatches:
        """Match one keyword. ``support`` (batch statistics) enables the batch-backed rules."""
        tokens = tuple(tokens)
        if not tokens:
            return KeywordMatches()
        brand_cache = character_cache = None
        if fuzzy_cache is not None:
            brand_cache = fuzzy_cache.setdefault(BRAND, {})
            character_cache = fuzzy_cache.setdefault(CHARACTER, {})
        brands = self._select(self._brands.candidates(tokens, support, brand_cache), tokens)
        characters = self._select(
            self._characters.candidates(tokens, support, character_cache), tokens
        )
        return self._resolve_overlaps(brands, characters)

    def match_keywords(self, keywords: Iterable[object]) -> dict[str, KeywordMatches]:
        """Match a batch of raw keywords; returns results keyed by normalized keyword."""
        unique = {normalize_text(k) for k in keywords}
        unique.discard("")
        token_lists = {k: tuple(k.split()) for k in unique}
        support = NgramSupport(token_lists.values(), self.config.max_window_tokens)
        cache: dict = {}
        return {k: self.match_tokens(t, support, cache) for k, t in token_lists.items()}

    def _admissible(self, match: Match, tokens: tuple[str, ...]) -> bool:
        entity = match.entity
        if entity.ambiguous:
            outside = tokens[: match.start] + tokens[match.end :]
            if not entity.context or not any(t in entity.context for t in outside):
                return False
        if (
            match.length == 1
            and tokens[match.start] in self.lexicon.units
            and match.start > 0
            and has_digit(tokens[match.start - 1])
        ):
            return False  # "motor 2 hp", "tornillo 6 mm"
        return True

    def _select(self, candidates: list[Match], tokens: tuple[str, ...]) -> list[Match]:
        """Leftmost-longest selection of non-overlapping admissible matches."""
        ordered = sorted(
            (m for m in candidates if self._admissible(m, tokens)),
            key=lambda m: (-m.length, _METHOD_RANK[m.method], -m.score, m.start, m.entity.entity_id),
        )
        chosen: list[Match] = []
        for match in ordered:
            if not any(match.overlaps(c) for c in chosen):
                chosen.append(match)
        return sorted(chosen, key=lambda m: (_METHOD_RANK[m.method], -m.score, m.start))

    def _resolve_overlaps(
        self, brands: list[Match], characters: list[Match]
    ) -> KeywordMatches:
        """Drop a match nested inside an unrelated longer match of the other kind.

        "jessica simpson" (brand) hides the character "simpson", and the
        character "max steel" hides the brand "max"; but "lego" stays next to
        the character "lego friends" because Lego owns that franchise.
        """
        stop = self.lexicon.stopwords

        def brand_belongs(brand: Match, character: Match) -> bool:
            words = set(brand.entity.tokens) - stop
            return bool(words) and words <= character.entity.related_terms

        def character_belongs(character: Match, brand: Match) -> bool:
            extra = set(brand.entity.tokens) - set(character.entity.tokens) - stop
            return bool(extra) and extra <= character.entity.related_terms

        kept_brands = [
            b
            for b in brands
            if not any(c.strictly_contains(b) and not brand_belongs(b, c) for c in characters)
        ]
        kept_characters = [
            c
            for c in characters
            if not any(b.strictly_contains(c) and not character_belongs(c, b) for b in brands)
        ]
        return KeywordMatches(tuple(kept_brands), tuple(kept_characters))
