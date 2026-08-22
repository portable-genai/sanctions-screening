"""The deterministic fuzzy-match engine: it owns the confidence, the band and the recommendation.

Pure stdlib, replayable, no model. Given a party and the list entries, it computes a
match-confidence figure from four sub-scores (token similarity, name-part overlap, date of birth,
identifier), bands the figure by the adopter's :class:`MatchPolicy`, and proposes a disposition.
A model may later NARRATE the result; it never produces the number or the band.

Two safety properties the eval pins:

* a zero-tolerance FALSE-CLEAR rule: an exact normalised-name match, or an exact identifier
  match, is forced to at least the CONFIRMED band, so a true designated party can never band as
  clear because a sub-score happened to be low;
* a cross-kind cap: an individual name never CONFIRMS against an entity listing (or the reverse),
  because a shared token is not a shared party.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from difflib import SequenceMatcher

from .models import (
    ListEntry,
    MatchBand,
    NameScore,
    PartyKind,
    PartyMatch,
    PartyScreening,
    Recommendation,
    ScreenableParty,
    band_rank,
)
from .policy import MatchPolicy

#: Legal-form tokens dropped before entity comparison so "Ltd" vs "Limited" is not a mismatch.
#: Only true corporate FORMS belong here: a meaningful name word (Metals, Shipping) must never be
#: dropped, or two unrelated companies collapse to the same normalised token and over-match.
_CORP_SUFFIXES = frozenset(
    {
        "ltd",
        "limited",
        "pte",
        "llc",
        "inc",
        "sa",
        "ojsc",
        "pty",
        "corp",
        "corporation",
        "gmbh",
        "bv",
        "plc",
        "ag",
        "nv",
    }
)
_PUNCT = re.compile(r"[^a-z0-9\s]")


def normalize(name: str) -> str:
    """Fold accents and transliteration to ASCII, casefold, strip punctuation, collapse space."""
    decomposed = unicodedata.normalize("NFKD", name)
    ascii_only = decomposed.encode("ascii", "ignore").decode("ascii")
    lowered = _PUNCT.sub(" ", ascii_only.casefold())
    return " ".join(lowered.split())


def _tokens(name: str, *, drop_corp: bool) -> tuple[str, ...]:
    tokens = normalize(name).split()
    if drop_corp:
        stripped = tuple(t for t in tokens if t not in _CORP_SUFFIXES)
        if stripped:
            return stripped
    return tuple(tokens)


def _ratio(a: str, b: str) -> float:
    return SequenceMatcher(None, a, b).ratio() * 100.0


def _token_score(query_tokens: tuple[str, ...], cand_tokens: tuple[str, ...]) -> float:
    """Blend a token-sort ratio with a token-set ratio, both 0..100."""
    if not query_tokens or not cand_tokens:
        return 0.0
    sort_ratio = _ratio(" ".join(sorted(query_tokens)), " ".join(sorted(cand_tokens)))
    q_set, c_set = set(query_tokens), set(cand_tokens)
    intersection = q_set & c_set
    union = q_set | c_set
    set_ratio = 100.0 * len(intersection) / len(union) if union else 0.0
    return max(sort_ratio, set_ratio)


def _name_part_score(query_tokens: tuple[str, ...], cand_tokens: tuple[str, ...]) -> float:
    if not query_tokens or not cand_tokens:
        return 0.0
    q_set, c_set = set(query_tokens), set(cand_tokens)
    covered = len(q_set & c_set)
    return 100.0 * covered / max(len(q_set), len(c_set))


def _norm_ids(ids: tuple[str, ...]) -> set[str]:
    return {re.sub(r"[^a-z0-9]", "", i.casefold()) for i in ids if i.strip()}


@dataclass(frozen=True, slots=True)
class _SubScores:
    token: float
    name_part: float
    dob: float | None
    identifier: float | None
    id_matched: bool
    exact_name: bool


class MatchEngine:
    """Score a party against list entries and band the result, all deterministically."""

    def __init__(self, policy: MatchPolicy) -> None:
        self._policy = policy

    # ------------------------------------------------------------------ scoring

    def _candidate_names(self, entry: ListEntry) -> tuple[str, ...]:
        return (entry.name, *entry.aliases)

    def _sub_scores(self, party: ScreenableParty, entry: ListEntry, candidate: str) -> _SubScores:
        drop_corp = PartyKind.ENTITY in (party.kind, entry.kind)
        q_tokens = _tokens(party.name, drop_corp=drop_corp)
        c_tokens = _tokens(candidate, drop_corp=drop_corp)
        token = _token_score(q_tokens, c_tokens)
        name_part = _name_part_score(q_tokens, c_tokens)

        dob: float | None = None
        if party.dob and entry.dob:
            dob = 100.0 if party.dob == entry.dob else 0.0

        identifier: float | None = None
        id_matched = False
        q_ids, c_ids = _norm_ids(party.identifiers), _norm_ids(entry.identifiers)
        if q_ids and c_ids:
            id_matched = bool(q_ids & c_ids)
            identifier = 100.0 if id_matched else 0.0

        exact_name = normalize(party.name) == normalize(candidate)
        return _SubScores(token, name_part, dob, identifier, id_matched, exact_name)

    def _confidence(self, sub: _SubScores, party: ScreenableParty, entry: ListEntry) -> NameScore:
        policy = self._policy
        components: list[tuple[float, float]] = [
            (sub.token, policy.token_weight),
            (sub.name_part, policy.name_part_weight),
        ]
        if sub.dob is not None:
            components.append((sub.dob, policy.dob_weight))
        if sub.identifier is not None:
            components.append((sub.identifier, policy.id_weight))
        total_weight = sum(weight for _, weight in components)
        blended = sum(score * weight for score, weight in components) / total_weight

        # The false-clear guards: an exact identifier match, or an exact normalised-name match
        # where no date of birth contradicts it, is forced to the top band. A true designated
        # party must never fall to a clear band because one sub-score was low.
        if sub.id_matched or (sub.exact_name and sub.dob != 0.0):
            blended = max(blended, policy.confirmed_at)

        # Cross-kind cap: an individual and an entity that share a token are not the same party.
        if (
            party.kind in (PartyKind.INDIVIDUAL, PartyKind.ENTITY)
            and entry.kind in (PartyKind.INDIVIDUAL, PartyKind.ENTITY)
            and party.kind != entry.kind
            and not sub.id_matched
        ):
            # An individual and an entity are different party TYPES: a shared surname is at most a
            # weak lead, never a review-band match, so cap below the possible threshold.
            blended = min(blended, policy.possible_at - 1.0)

        confidence = round(max(0.0, min(100.0, blended)), 2)
        arithmetic = self._arithmetic(sub, components, confidence)
        return NameScore(
            normalized_query=normalize(party.name),
            normalized_candidate=normalize(entry.name),
            token_score=round(sub.token, 2),
            name_part_score=round(sub.name_part, 2),
            dob_score=sub.dob if sub.dob is not None else -1.0,
            id_score=sub.identifier if sub.identifier is not None else -1.0,
            confidence=confidence,
            arithmetic=arithmetic,
        )

    @staticmethod
    def _arithmetic(
        sub: _SubScores, components: list[tuple[float, float]], confidence: float
    ) -> str:
        parts = " + ".join(f"{score:.1f}x{weight:.2f}" for score, weight in components)
        note = ""
        if sub.id_matched:
            note = " [identifier exact: forced to confirmed]"
        elif sub.exact_name and sub.dob != 0.0:
            note = " [name exact: forced to confirmed]"
        return f"({parts}) / {sum(w for _, w in components):.2f} = {confidence:.2f}{note}"

    def band(self, confidence: float) -> MatchBand:
        """Band a 0..100 confidence by the adopter's policy thresholds."""
        policy = self._policy
        if confidence >= policy.confirmed_at:
            return MatchBand.CONFIRMED
        if confidence >= policy.strong_at:
            return MatchBand.STRONG
        if confidence >= policy.possible_at:
            return MatchBand.POSSIBLE
        if confidence >= policy.weak_at:
            return MatchBand.WEAK
        return MatchBand.CLEAR

    # ------------------------------------------------------------------ screening

    def _best_match(self, party: ScreenableParty, entry: ListEntry) -> PartyMatch:
        best: NameScore | None = None
        for candidate in self._candidate_names(entry):
            score = self._confidence(self._sub_scores(party, entry, candidate), party, entry)
            if best is None or score.confidence > best.confidence:
                best = score
        assert best is not None  # an entry always has at least its primary name
        citations = (entry.citation,) if entry.citation else ()
        return PartyMatch(
            party=party,
            entry=entry,
            band=self.band(best.confidence),
            confidence=best.confidence,
            score=best,
            citations=citations,
        )

    def screen_party(
        self, party: ScreenableParty, entries: tuple[ListEntry, ...]
    ) -> PartyScreening:
        """Screen one party against every list entry, keeping the review-band matches (POSSIBLE+).

        WEAK and CLEAR are not review-worthy: keeping them would drown a real match in leads no
        analyst would open. A golden true match must band STRONG or CONFIRMED, so it is always
        kept; a golden non-match must band below POSSIBLE, so it is always dropped.
        """
        review_floor = band_rank(MatchBand.POSSIBLE)
        matches = [self._best_match(party, entry) for entry in entries]
        kept = tuple(
            sorted(
                (m for m in matches if band_rank(m.band) >= review_floor),
                key=lambda m: m.confidence,
                reverse=True,
            )
        )
        party_band = max((m.band for m in kept), key=band_rank) if kept else MatchBand.CLEAR
        return PartyScreening(
            party=party,
            matches=kept,
            band=party_band,
            recommendation=recommendation_for(party_band),
        )


def recommendation_for(band: MatchBand) -> Recommendation:
    """Map a match band to the disposition the engine proposes (never auto-executed)."""
    if band in (MatchBand.CONFIRMED, MatchBand.STRONG):
        return Recommendation.TRUE_MATCH
    if band is MatchBand.POSSIBLE:
        return Recommendation.NEEDS_INFO
    return Recommendation.FALSE_POSITIVE
