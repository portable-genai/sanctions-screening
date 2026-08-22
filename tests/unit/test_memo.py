"""The disposition memo: grounded builder, groundedness check, and the discard-and-fallback path."""

from __future__ import annotations

from collections.abc import Mapping

from sanctions_screening.adapters.local.narration import LocalNarrationAdapter
from sanctions_screening.adapters.local.ownership_graph import FIXTURE_TENANT
from sanctions_screening.config import Settings, build_container
from sanctions_screening.domain.listpacks import load_guidance, load_list_entries
from sanctions_screening.domain.match_engine import MatchEngine
from sanctions_screening.domain.memo import build_memo, is_grounded
from sanctions_screening.domain.models import PartyKind, ScreeningRequest, ScreeningResult
from sanctions_screening.domain.policy import MatchPolicy
from sanctions_screening.domain.screening_service import ScreeningService

from tests.conftest import local_settings

_FACTS: dict[str, object] = {
    "subject": "Volkov Metals OJSC (FICTIONAL)",
    "band": "confirmed",
    "recommendation": "true_match",
    "matches": [
        {
            "name": "Volkov Metals OJSC (FICTIONAL)",
            "list_id": "UN",
            "entry": "UN-1001",
            "confidence": 100.0,
        }
    ],
    "owner_matches": [],
    "owners_screened": 0,
    "adverse_media": [],
    "guidance": "",
}


def test_the_deterministic_memo_is_grounded() -> None:
    memo = build_memo(_FACTS)
    assert is_grounded(memo, _FACTS)
    assert "100.0" in memo


def test_a_fabricated_number_is_not_grounded() -> None:
    fabricated = build_memo(_FACTS) + " The party held a 42.5 percent stake."
    assert not is_grounded(fabricated, _FACTS)


def test_an_identifier_digit_from_the_facts_is_allowed() -> None:
    """UN-1001 carries digits a grounded memo may quote; only a NEW number is a fabrication."""
    assert is_grounded("Matched UN entry UN-1001.", _FACTS)


class _HallucinatingNarration:
    """A narration adapter that invents a number the engine never computed."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def draft_memo(self, facts: Mapping[str, object]) -> str:
        return "The subject held a 73.2 percent controlling stake (fabricated)."


def _service_with(narration: object) -> ScreeningService:
    container = build_container(local_settings())
    policy = MatchPolicy()
    return ScreeningService(
        container.audit,
        container.ownership_graph,
        container.adverse_media,
        narration,  # type: ignore[arg-type]
        tracer=container.tracer,
        engine=MatchEngine(policy),
        list_entries=load_list_entries(),
        guidance=load_guidance(),
        policy=policy,
    )


def test_an_ungrounded_draft_is_discarded_and_the_fallback_is_used() -> None:
    service = _service_with(_HallucinatingNarration(local_settings()))
    result = service.screen(
        ScreeningRequest(subject="Volkov Metals OJSC (FICTIONAL)", kind=PartyKind.ENTITY),
        actor="a",
    )
    # The fabricated draft is discarded (grounded=False marks the fallback), and its invented
    # number never reaches the memo shown to a reviewer.
    assert result.memo.grounded is False
    assert "73.2" not in result.memo.text
    assert result.memo.text.strip(), "the fallback memo must still be a real, cited memo"


class _SilentGeneration:
    """The generation adapter 'stubbed out': it produces no narration at all."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def draft_memo(self, facts: Mapping[str, object]) -> str:
        return ""


def _numbers(result: ScreeningResult) -> tuple[object, ...]:
    """Every consequential number and verdict the engine owns, as a comparable fingerprint.

    Deliberately excludes ``memo.text`` and ``memo.grounded``: those are the ONLY fields the
    narrator is allowed to move.
    """
    return (
        result.band,
        result.recommendation,
        result.severity,
        result.decision,
        result.owners_screened,
        result.requires_human_review,
        result.summary,
        tuple(
            (
                screening.party.name,
                screening.party.role,
                screening.band,
                screening.recommendation,
                tuple(
                    (match.entry.list_id, match.entry.entry_id, match.confidence, match.band)
                    for match in screening.matches
                ),
            )
            for screening in result.party_screenings
        ),
    )


def test_the_numbers_are_identical_with_the_generation_adapter_stubbed_out() -> None:
    """The house determinism invariant: the model narrates, it never produces a number.

    Screen the same subject three ways: the real deterministic narration, the generation adapter
    stubbed to silence, and a narration that hallucinates a figure. Every consequential number and
    verdict (band, confidence, recommendation, severity, owner count) is IDENTICAL across all
    three; only the memo prose differs. A number that moved when the narrator changed would be a
    number the narrator produced, which is exactly what this architecture forbids.
    """
    request = ScreeningRequest(
        subject="Acme Holdings Pte Ltd (FICTIONAL)", kind=PartyKind.ENTITY, subject_id="acme"
    )
    real = _service_with(LocalNarrationAdapter(local_settings())).screen(
        request, actor="a", tenant=FIXTURE_TENANT
    )
    stubbed = _service_with(_SilentGeneration(local_settings())).screen(
        request, actor="a", tenant=FIXTURE_TENANT
    )
    invented = _service_with(_HallucinatingNarration(local_settings())).screen(
        request, actor="a", tenant=FIXTURE_TENANT
    )

    assert _numbers(real) == _numbers(stubbed) == _numbers(invented)
    # The subject resolves a listed beneficial owner, so there is a real, consequential number
    # (the owner band and its confidence) that the stub run could have disturbed and did not.
    assert real.owners_screened == 2
    # The narrator moved only the memo: silence and a discarded hallucination both fall back to
    # the deterministic memo, while the real adapter's grounded draft stands.
    assert real.memo.grounded is True
    assert stubbed.memo.grounded is False and invented.memo.grounded is False
    assert "73.2" not in invented.memo.text
