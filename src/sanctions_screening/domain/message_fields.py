"""Deterministic party extraction from a payment message (ISO 20022 / SWIFT MT).

Pure stdlib, no model. A payment message names several parties (the ordering customer, the
beneficiary, their ultimate parties); each must be screened, so this module turns a mapping of
message fields into typed :class:`ScreenableParty` records. The field-to-role map is DATA, so a
new message flavour is a table entry rather than a code branch.

The extraction decides nothing: it gathers the parties a downstream engine screens. Extraction
exactness is measured against golden messages in the eval.
"""

from __future__ import annotations

from .models import PartyKind, PartyRole, ScreenableParty

#: Field id -> (role, kind). ISO 20022 element names (``Dbtr/Nm``) and SWIFT MT tags (``50K``)
#: both appear, because a screening desk sees both on the same wire. A field absent from a given
#: message is simply skipped; a field present but empty contributes no party.
_FIELD_MAP: dict[str, tuple[PartyRole, PartyKind]] = {
    # ISO 20022 pain.001 / pacs.008 element names.
    "Dbtr/Nm": (PartyRole.DEBTOR, PartyKind.UNKNOWN),
    "Cdtr/Nm": (PartyRole.CREDITOR, PartyKind.UNKNOWN),
    "UltmtDbtr/Nm": (PartyRole.ULTIMATE_DEBTOR, PartyKind.UNKNOWN),
    "UltmtCdtr/Nm": (PartyRole.ULTIMATE_CREDITOR, PartyKind.UNKNOWN),
    # SWIFT MT103 tags.
    "50K": (PartyRole.DEBTOR, PartyKind.UNKNOWN),
    "50F": (PartyRole.DEBTOR, PartyKind.UNKNOWN),
    "59": (PartyRole.CREDITOR, PartyKind.UNKNOWN),
    "59F": (PartyRole.CREDITOR, PartyKind.UNKNOWN),
}

#: Companion country fields, so a party carries a jurisdiction when the message states one.
_COUNTRY_SUFFIX = "/CtryOfRes"


def _clean(value: str) -> str:
    """First non-empty line of a field, whitespace-normalised. SWIFT stacks lines with ``\\n``."""
    for line in value.replace("\r", "\n").split("\n"):
        stripped = " ".join(line.split())
        if stripped:
            return stripped
    return ""


def extract_parties(message: tuple[tuple[str, str], ...]) -> tuple[ScreenableParty, ...]:
    """Turn ordered message field pairs into the parties to screen, in a stable order.

    A field is read once; an unknown field is ignored rather than guessed at. The ``party_id`` is
    the field id, so a match traces back to the exact wire element it came from.
    """
    fields = dict(message)
    parties: list[ScreenableParty] = []
    for field_id, (role, kind) in _FIELD_MAP.items():
        name = _clean(fields.get(field_id, ""))
        if not name:
            continue
        jurisdiction = _clean(fields.get(field_id.split("/")[0] + _COUNTRY_SUFFIX, ""))
        parties.append(
            ScreenableParty(
                party_id=field_id,
                name=name,
                role=role,
                kind=kind,
                jurisdiction=jurisdiction,
                source_ref=field_id,
            )
        )
    return tuple(parties)
