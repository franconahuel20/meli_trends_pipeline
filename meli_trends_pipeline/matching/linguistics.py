"""Lemmas and parts of speech of trend keywords (``lemmatized_keyword_str``, ``nouns_keyword_str``).

The pipeline uses spaCy's small Spanish and Portuguese models (Brazilian keywords are
Portuguese). :class:`SimpleAnalyzer` is a dependency-free stand-in for unit tests.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Protocol, Sequence

from .lexicon import Lexicon
from .text import normalize_text

SPANISH = "es"
PORTUGUESE = "pt"
SPACY_MODELS = {SPANISH: "es_core_news_sm", PORTUGUESE: "pt_core_news_sm"}
NOUN = "NOUN"


@dataclass(frozen=True)
class Token:
    text: str
    lemma: str
    pos: str


class KeywordAnalyzer(Protocol):
    def analyze(self, texts: Sequence[str], language: str) -> list[list[Token]]:
        """Tokens of every text, in order."""


def language_of(country: object) -> str:
    return PORTUGUESE if normalize_text(country) in {"brasil", "brazil"} else SPANISH


def keyword_text(value: object) -> str:
    """Keyword as given to the analyzer: lowercase, single spaces, accents kept."""
    return " ".join(str(value).lower().split()) if value is not None else ""


class SpacyAnalyzer:
    """spaCy tagger + lemmatizer; models are loaded on first use, results are cached."""

    def __init__(self, batch_size: int = 2000) -> None:
        self._batch_size = batch_size
        self._models: dict = {}
        self._cache: dict[tuple[str, str], list[Token]] = {}

    def _model(self, language: str):
        if language not in self._models:
            import spacy

            # Only the tagger and lemmatizer are needed: parser and NER are skipped for speed.
            self._models[language] = spacy.load(SPACY_MODELS[language], exclude=["parser", "ner"])
        return self._models[language]

    def analyze(self, texts: Sequence[str], language: str) -> list[list[Token]]:
        pending = list(dict.fromkeys(t for t in texts if (t, language) not in self._cache))
        if pending:
            nlp = self._model(language)
            for text, doc in zip(pending, nlp.pipe(pending, batch_size=self._batch_size)):
                self._cache[(text, language)] = [
                    Token(t.text, (t.lemma_ or t.text).lower(), t.pos_) for t in doc if not t.is_space
                ]
        return [self._cache[(t, language)] for t in texts]


class SimpleAnalyzer:
    """Whitespace tokens, no lemmatization; every non-stopword, non-number token is a noun."""

    def __init__(self, lexicon: Lexicon | None = None) -> None:
        self._lexicon = lexicon or Lexicon.load()

    def analyze(self, texts: Sequence[str], language: str) -> list[list[Token]]:
        out = []
        for text in texts:
            tokens = []
            for word in text.split():
                norm = normalize_text(word)
                noun = bool(norm) and not norm.isdigit() and not self._lexicon.is_stopword(norm)
                tokens.append(Token(word, word, NOUN if noun else "X"))
            out.append(tokens)
        return out


def lemmatized(tokens: Iterable[Token]) -> str | None:
    return " ".join(t.lemma for t in tokens) or None


def nouns(tokens: Iterable[Token], excluded: set[str], lexicon: Lexicon) -> str | None:
    """Lemmas of the nouns, leaving out brand/character words, stopwords and numbers."""
    words = []
    for token in tokens:
        if token.pos != NOUN:
            continue
        parts = normalize_text(token.text).split()
        if not parts or all(p in excluded for p in parts):
            continue
        if len(parts) == 1 and (lexicon.is_stopword(parts[0]) or parts[0].isdigit()):
            continue
        words.append(token.lemma)
    return " ".join(words) or None
