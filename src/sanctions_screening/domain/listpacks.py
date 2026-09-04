"""Load sanctions / PEP list packs and jurisdiction guidance packs, as DATA.

The lists screened against and the procedure guidance cited in a memo are data files, not code, so a
list update is a pack edit under review rather than a code change (the marketing-compliance-gate
pack convention). Packs are JSON rather than YAML for one reason: this module is pure-stdlib domain
code, and ``json`` is stdlib while a YAML parser is a third-party dependency the domain must not
import. Every entry is obviously fictional.

Two shapes share the ``rulepacks/`` directory:

* a LIST pack carries ``entries`` (the reference parties screened against);
* a GUIDANCE pack carries ``guidance`` (per-jurisdiction procedure notes the memo cites).

:func:`validate_pack` is the pack-schema check the eval scores at 1.0; a malformed pack is a
build-visible failure, not a silently dropped list.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import dataclass
from importlib import resources

from .kernel import Citation
from .models import ListEntry, PartyKind

_PACK_ANCHOR = "sanctions_screening.rulepacks"


@dataclass(frozen=True, slots=True)
class GuidanceNote:
    """One jurisdiction's screening-procedure guidance, cited in the disposition memo."""

    jurisdiction: str
    authority: str
    text: str
    citation: Citation


def _read_packs() -> list[dict[str, object]]:
    packs: list[dict[str, object]] = []
    for entry in resources.files(_PACK_ANCHOR).iterdir():
        if entry.name.endswith(".json"):
            packs.append(json.loads(entry.read_text(encoding="utf-8")))
    return packs


def validate_pack(pack: dict[str, object]) -> list[str]:
    """Return the list of schema problems in one pack (empty means valid)."""
    problems: list[str] = []
    if not isinstance(pack.get("list_id"), str) or not pack.get("list_id"):
        problems.append("missing 'list_id'")
    entries = pack.get("entries")
    guidance = pack.get("guidance")
    if entries is None and guidance is None:
        problems.append("a pack must carry 'entries' or 'guidance'")
    if entries is not None:
        if not isinstance(entries, list):
            problems.append("'entries' must be a list")
        else:
            for index, raw in enumerate(entries):
                if not isinstance(raw, dict):
                    problems.append(f"entry {index} is not an object")
                    continue
                for required in ("entry_id", "name", "kind"):
                    if not raw.get(required):
                        problems.append(f"entry {index} missing '{required}'")
                kind = raw.get("kind")
                if isinstance(kind, str) and kind not in tuple(PartyKind):
                    problems.append(f"entry {index} has unknown kind {kind!r}")
    return problems


def validate_all_packs() -> list[str]:
    """Validate every shipped pack, returning a flat list of problems across all of them."""
    problems: list[str] = []
    for pack in _read_packs():
        list_id = str(pack.get("list_id", "<unknown>"))
        problems.extend(f"{list_id}: {p}" for p in validate_pack(pack))
    return problems


def _str_tuple(value: object) -> tuple[str, ...]:
    """A pack field that is absent, null or a list of scalars, coerced to a tuple of strings."""
    return tuple(str(v) for v in value) if isinstance(value, (list, tuple)) else ()


def _entry(list_id: str, program: str, raw: dict[str, object]) -> ListEntry:
    citation = Citation(
        source_id=f"list:{list_id}:{raw['entry_id']}",
        title=f"{list_id} listing {raw['entry_id']}",
        snippet=str(raw.get("program") or program),
    )
    return ListEntry(
        list_id=list_id,
        entry_id=str(raw["entry_id"]),
        name=str(raw["name"]),
        kind=PartyKind(str(raw["kind"])),
        aliases=_str_tuple(raw.get("aliases")),
        dob=str(raw.get("dob") or ""),
        identifiers=_str_tuple(raw.get("identifiers")),
        program=str(raw.get("program") or program),
        citation=citation,
    )


def load_list_entries(packs: Iterable[dict[str, object]] | None = None) -> tuple[ListEntry, ...]:
    """Load every list entry from every list pack, refusing a malformed pack loudly.

    A pack that fails :func:`validate_pack` raises rather than contributing partial data: a
    silently dropped list entry is a screening gap that looks exactly like a clean screen.
    """
    entries: list[ListEntry] = []
    for pack in packs if packs is not None else _read_packs():
        if "entries" not in pack:
            continue
        problems = validate_pack(pack)
        if problems:
            raise ValueError(f"list pack {pack.get('list_id')!r} is invalid: {problems}")
        # validate_pack proved 'entries' is a list of objects carrying the required keys; these
        # isinstance narrowings restate that for the type checker without widening what is read.
        raw_entries = pack["entries"]
        assert isinstance(raw_entries, list)
        list_id = str(pack["list_id"])
        program = str(pack.get("program") or "")
        for raw in raw_entries:
            assert isinstance(raw, dict)
            entries.append(_entry(list_id, program, raw))
    return tuple(entries)


def load_guidance() -> tuple[GuidanceNote, ...]:
    """Load the per-jurisdiction procedure guidance notes cited in a disposition memo."""
    notes: list[GuidanceNote] = []
    for pack in _read_packs():
        guidance = pack.get("guidance")
        if not isinstance(guidance, list):
            continue
        list_id = str(pack.get("list_id", ""))
        for raw in guidance:
            if not isinstance(raw, dict):
                continue
            jurisdiction = str(raw.get("jurisdiction") or "")
            authority = str(raw.get("authority") or list_id)
            citation = Citation(
                source_id=f"guidance:{list_id}:{jurisdiction}",
                title=f"{authority} screening guidance",
                snippet=str(raw.get("text") or "")[:120],
            )
            notes.append(
                GuidanceNote(
                    jurisdiction=jurisdiction,
                    authority=authority,
                    text=str(raw.get("text") or ""),
                    citation=citation,
                )
            )
    return tuple(notes)
