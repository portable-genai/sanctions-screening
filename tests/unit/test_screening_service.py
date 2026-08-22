"""The screening orchestrator: deterministic bands, owner screening, redact-before-audit, R8."""

from __future__ import annotations

import json
from dataclasses import asdict

from sanctions_screening.adapters._review_payload import result_to_review
from sanctions_screening.adapters.local.ownership_graph import FIXTURE_TENANT
from sanctions_screening.config import build_container
from sanctions_screening.domain.models import (
    MatchBand,
    PartyKind,
    Recommendation,
    ScreeningRequest,
)
from sanctions_screening.service_factory import build_screening_service

from tests.conftest import local_settings
from tests.fixtures import sample_cases


def _service(**overrides: object):
    return build_screening_service(build_container(local_settings(**overrides)))


def test_a_designated_entity_confirms_and_always_requires_review() -> None:
    result = _service().screen(
        ScreeningRequest(subject="Volkov Metals OJSC (FICTIONAL)", kind=PartyKind.ENTITY),
        actor="analyst@bank.example",
    )
    assert result.band is MatchBand.CONFIRMED
    assert result.recommendation is Recommendation.TRUE_MATCH
    # The system never clears a match on its own: every disposition routes to a human.
    assert result.requires_human_review is True
    assert result.citations, "a disposition must be cited"


def test_a_clean_name_bands_clear_but_still_requires_review() -> None:
    result = _service().screen(
        ScreeningRequest(subject="Beta Stationery Pte Ltd (FICTIONAL)", kind=PartyKind.ENTITY),
        actor="a",
    )
    assert result.band is MatchBand.CLEAR
    assert result.recommendation is Recommendation.FALSE_POSITIVE
    assert result.requires_human_review is True


def test_the_band_is_deterministic_across_runs() -> None:
    request = ScreeningRequest(subject="Redsea Shipping Ltd (FICTIONAL)", kind=PartyKind.ENTITY)
    first = _service().screen(request, actor="a")
    second = _service().screen(request, actor="a")
    assert first.band == second.band == MatchBand.CONFIRMED
    assert first.summary == second.summary


def test_beneficial_owners_are_screened_and_a_listed_owner_is_caught() -> None:
    result = _service().screen(
        ScreeningRequest(
            subject="Acme Holdings Pte Ltd (FICTIONAL)",
            kind=PartyKind.ENTITY,
            subject_id="acme",
        ),
        actor="a",
        tenant=FIXTURE_TENANT,
    )
    assert result.owners_screened == 2
    owner_bands = {
        s.party.name: s.band
        for s in result.party_screenings
        if s.party.role.value == "beneficial_owner"
    }
    # Ines Quiller is a PEP in the fixture list, so the owner path catches her.
    assert owner_bands["Ines Quiller (FICTIONAL)"] is MatchBand.CONFIRMED


def test_pii_is_redacted_before_the_audit_write() -> None:
    settings = local_settings()
    container = build_container(settings)
    service = build_screening_service(container)
    service.screen(
        ScreeningRequest(
            subject="Dmitri Volkov (FICTIONAL)",
            kind=PartyKind.INDIVIDUAL,
            context="NRIC S1234567D on file",
        ),
        actor="analyst@bank.example",
    )
    records = container.audit.log.read_all()
    assert records, "an audit event should have been recorded"
    summary = records[-1]["redacted_summary"]
    assert "S1234567D" not in summary
    assert "REDACTED" in summary
    assert records[-1]["actor"] == "analyst@bank.example"
    assert container.audit.log.verify_chain().ok


def test_no_planted_identifier_reaches_the_model_the_worm_record_or_the_console() -> None:
    """The three sinks, one test: what the model reads, what the WORM record keeps, what leaves.

    The subject key and the analyst's context take different routes. The context was masked on
    its way into the audit summary; the SUBJECT went into the memo facts verbatim, so the model
    read the national id of the person being screened. The owner names Doc1 resolves travel the
    same route and are not the caller's text at all: they are natural persons named by another
    service, and they reached the memo facts unmasked too.

    The audit scan reads the citations as well as the summary, because a metric that reads the
    one masked field is how this class of defect stays invisible.
    """
    seen: list[dict[str, object]] = []
    container = build_container(local_settings())
    service = build_screening_service(container)
    inner = service._narration  # noqa: SLF001 - tapping the port is the point of the test

    class _Tap:
        def draft_memo(self, facts: dict[str, object]) -> str:
            seen.append(facts)
            return inner.draft_memo(facts)

    service._narration = _Tap()  # type: ignore[assignment]  # noqa: SLF001
    result = service.screen(sample_cases.PII_SUBJECT_CASE, actor=sample_cases.ACTOR)
    planted = (sample_cases.PLANTED_NRIC, sample_cases.PLANTED_EMAIL)

    # 1. The model. The WHOLE facts object, not the fields somebody remembered to mask.
    assert seen, "the narrator must have been called"
    read_by_model = json.dumps(seen[-1], default=str)
    for token in planted:
        assert token not in read_by_model, f"{token} reached the model in {read_by_model!r}"

    # 2. The WORM record. Content fields only: `actor` is the verified principal and is an
    #    address by design, so scanning it would make this unfailable in the wrong direction.
    rows = [dict(row) for row in container.audit.log.read_all()]
    assert rows
    for row in rows:
        stored = row["redacted_summary"] + json.dumps(row["citations"], default=str)
        for token in planted:
            assert token not in stored, f"{token} survived into the WORM record: {stored!r}"

    # 3. What LEAVES for the review console (rule R8), locator and source key included.
    outbound = json.dumps(
        asdict(result_to_review(result, maker=sample_cases.ACTOR, tenant=sample_cases.TENANT)),
        default=str,
    )
    for token in planted:
        assert token not in outbound, f"{token} left for Hrz7 in {outbound!r}"


def test_adverse_media_is_advisory_and_does_not_move_the_band() -> None:
    """The band is the engine's alone; adverse media enriches the memo, nothing else."""
    result = _service().screen(
        ScreeningRequest(subject="Dmitri Volkov (FICTIONAL)", kind=PartyKind.INDIVIDUAL),
        actor="a",
    )
    assert result.adverse_media, "the fixture corpus should surface a finding for this name"
    assert result.band is MatchBand.CONFIRMED  # the finding did not change the band


def test_the_memo_is_grounded_on_the_offline_profile() -> None:
    result = _service().screen(
        ScreeningRequest(subject="Volkov Metals OJSC (FICTIONAL)", kind=PartyKind.ENTITY),
        actor="a",
    )
    assert result.memo.grounded is True
    assert result.memo.text.strip()
