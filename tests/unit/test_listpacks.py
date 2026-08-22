"""List and guidance packs load as valid DATA, and a malformed pack fails loudly."""

from __future__ import annotations

import pytest

from sanctions_screening.domain.listpacks import (
    load_guidance,
    load_list_entries,
    validate_all_packs,
    validate_pack,
)
from sanctions_screening.domain.models import PartyKind


def test_every_shipped_pack_is_schema_valid() -> None:
    assert validate_all_packs() == [], "a shipped pack failed schema validation"


def test_list_entries_load_across_multiple_lists() -> None:
    entries = load_list_entries()
    list_ids = {e.list_id for e in entries}
    assert {"UN", "OFAC", "EU", "AU-DFAT", "PEP"} <= list_ids
    assert all(e.citation is not None for e in entries), "every entry carries provenance"


def test_guidance_notes_carry_a_citation() -> None:
    notes = load_guidance()
    assert notes
    assert all(note.citation.source_id for note in notes)


def test_a_pack_missing_a_required_field_is_reported() -> None:
    bad = {"list_id": "BAD", "entries": [{"name": "No id (FICTIONAL)", "kind": "entity"}]}
    problems = validate_pack(bad)
    assert any("entry_id" in p for p in problems)


def test_a_pack_with_an_unknown_kind_is_reported() -> None:
    bad = {
        "list_id": "BAD",
        "entries": [{"entry_id": "x", "name": "Y (FICTIONAL)", "kind": "spaceship"}],
    }
    assert any("unknown kind" in p for p in validate_pack(bad))


def test_load_refuses_a_malformed_pack() -> None:
    with pytest.raises(ValueError, match="invalid"):
        load_list_entries([{"list_id": "BAD", "entries": [{"name": "x", "kind": "entity"}]}])


def test_known_kinds_are_the_party_kinds() -> None:
    assert "entity" in tuple(PartyKind)
