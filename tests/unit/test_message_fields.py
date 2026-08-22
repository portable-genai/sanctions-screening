"""Deterministic party extraction from ISO 20022 / SWIFT payment message fields."""

from __future__ import annotations

from sanctions_screening.domain.message_fields import extract_parties
from sanctions_screening.domain.models import PartyRole


def _message(**fields: str) -> tuple[tuple[str, str], ...]:
    return tuple(fields.items())


def test_iso20022_debtor_and_creditor_are_extracted() -> None:
    parties = extract_parties(
        (
            ("Dbtr/Nm", "Alpha Traders (FICTIONAL)"),
            ("Cdtr/Nm", "Redsea Shipping Ltd (FICTIONAL)"),
        )
    )
    roles = {p.role: p.name for p in parties}
    assert roles[PartyRole.DEBTOR] == "Alpha Traders (FICTIONAL)"
    assert roles[PartyRole.CREDITOR] == "Redsea Shipping Ltd (FICTIONAL)"


def test_swift_tags_are_extracted() -> None:
    parties = extract_parties(
        (("50K", "Alpha Traders (FICTIONAL)"), ("59", "Beta Ltd (FICTIONAL)"))
    )
    assert {p.role for p in parties} == {PartyRole.DEBTOR, PartyRole.CREDITOR}


def test_a_multiline_swift_field_takes_the_first_nonempty_line() -> None:
    parties = extract_parties((("59", "\n  Redsea Shipping Ltd (FICTIONAL)\n  123 Ocean Rd\n"),))
    assert parties[0].name == "Redsea Shipping Ltd (FICTIONAL)"


def test_an_empty_or_unknown_field_contributes_no_party() -> None:
    parties = extract_parties((("Dbtr/Nm", ""), ("SomethingElse", "ignored")))
    assert parties == ()


def test_the_party_id_traces_back_to_the_wire_element() -> None:
    parties = extract_parties((("UltmtDbtr/Nm", "Gamma Holdings (FICTIONAL)"),))
    assert parties[0].party_id == "UltmtDbtr/Nm"
    assert parties[0].role is PartyRole.ULTIMATE_DEBTOR
