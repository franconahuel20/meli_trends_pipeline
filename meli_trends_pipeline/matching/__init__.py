"""Brand and character matching for Mercado Libre trend keywords."""

from .enrichment import L3_COLUMNS, build_matcher, enrich_trends
from .lexicon import Lexicon
from .matcher import EntityMatcher, MatchingConfig
from .text import normalize_text

__all__ = [
    "L3_COLUMNS",
    "EntityMatcher",
    "Lexicon",
    "MatchingConfig",
    "build_matcher",
    "enrich_trends",
    "normalize_text",
]
