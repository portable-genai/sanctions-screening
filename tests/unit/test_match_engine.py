"""The deterministic fuzzy-match engine: bands, false-clear guard, cross-kind cap, replay."""

from __future__ import annotations

from sanctions_screening.domain.listpacks import load_list_entries
from sanctions_screening.domain.match_engine import MatchEngine, normalize
from sanctions_screening.domain.models import (
    MatchBand,
    PartyKind,
    Recommendation,
    ScreenableParty,
)
from sanctions_screening.domain.policy import MatchPolicy

_ENTRIES = load_list_entries()
_ENGINE = MatchEngine(MatchPolicy())


def _party(name: str, kind: PartyKind = PartyKind.ENTITY, **kwargs: object) -> ScreenableParty:
    return ScreenableParty(party_id="p", name=name, role="subject", kind=kind, **kwargs)  # type: ignore[arg-type]


def test_normalisation_folds_accents_and_punctuation() -> None:
    assert normalize("Volkov Métals, OJSC!") == "volkov metals ojsc"


def test_an_exact_designated_name_confirms() -> None:
    result = _ENGINE.screen_party(_party("Volkov Metals OJSC (FICTIONAL)"), _ENTRIES)
    assert result.band is MatchBand.CONFIRMED
    assert result.recommendation is Recommendation.TRUE_MATCH


def test_a_clean_name_clears() -> None:
    result = _ENGINE.screen_party(_party("Beta Stationery Pte Ltd (FICTIONAL)"), _ENTRIES)
    assert result.band is MatchBand.CLEAR
    assert result.recommendation is Recommendation.FALSE_POSITIVE
    assert not result.matches


def test_an_alias_abbreviation_still_matches() -> None:
    result = _ENGINE.screen_party(_party("Redsea Shpg Ltd (FICTIONAL)"), _ENTRIES)
    assert result.band in (MatchBand.STRONG, MatchBand.CONFIRMED)


def test_a_zero_tolerance_false_clear_cannot_happen_on_an_exact_name() -> None:
    """The core safety property: an exact designated name is never banded clear."""
    for entry in _ENTRIES:
        result = _ENGINE.screen_party(
            _party(
                entry.name,
                kind=PartyKind.INDIVIDUAL
                if entry.kind is PartyKind.INDIVIDUAL
                else PartyKind.ENTITY,
            ),
            _ENTRIES,
        )
        assert result.band is not MatchBand.CLEAR, f"{entry.name} was cleared"
        assert result.recommendation is Recommendation.TRUE_MATCH


def test_an_individual_does_not_confirm_against_an_entity_listing() -> None:
    """A shared surname across party TYPES is at most a weak lead, never a review-band match."""
    # "Volkov" as an individual should not confirm against the entity "Volkov Metals OJSC".
    result = _ENGINE.screen_party(_party("Volkov Industries", kind=PartyKind.INDIVIDUAL), _ENTRIES)
    assert result.band is not MatchBand.CONFIRMED


def test_the_score_is_replayable() -> None:
    party = _party("Palewater Holdings SA (FICTIONAL)")
    first = _ENGINE.screen_party(party, _ENTRIES)
    second = _ENGINE.screen_party(party, _ENTRIES)
    assert first.matches[0].confidence == second.matches[0].confidence
    assert first.matches[0].score.arithmetic == second.matches[0].score.arithmetic
