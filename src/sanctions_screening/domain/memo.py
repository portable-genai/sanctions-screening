"""The disposition-memo facts, the deterministic builder, and the groundedness check.

Pure stdlib. The memo is the one place a model narrates, so the guard against a hallucinated
number lives here where both the narrator's fallback and the validator can share it:

* :func:`build_memo` composes a grounded memo from the engine facts alone. The local narration
  adapter returns this, and the service uses it as the FALLBACK when a model draft is discarded,
  so a discarded draft never degrades below a real, cited memo.
* :func:`allowed_numbers` is the exact set of numeric tokens the engine computed.
* :func:`is_grounded` rejects any draft that contains a number outside that set: a model may
  restate the engine's figures and add nothing consequential, and a draft that invents "held 88%"
  is discarded rather than shown.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Any

_NUMBER = re.compile(r"\d+(?:\.\d+)?")


def fmt_pct(value: float) -> str:
    """The one formatting of a percentage, shared by the builder and the allowed-number set."""
    return f"{float(value):.1f}"


def _matches(facts: Mapping[str, Any]) -> Sequence[Mapping[str, Any]]:
    raw = facts.get("matches") or ()
    return [m for m in raw if isinstance(m, Mapping)]


def _owner_matches(facts: Mapping[str, Any]) -> Sequence[Mapping[str, Any]]:
    raw = facts.get("owner_matches") or ()
    return [m for m in raw if isinstance(m, Mapping)]


def _numbers_in_values(node: Any, out: set[str]) -> None:
    """Collect every numeric token that already appears in the facts' own string values.

    Identifiers and entry ids carry digits (``UN-1001``) that a grounded memo may legitimately
    quote. Only a number the engine did NOT put anywhere in the facts is a fabrication, so those
    embedded digits are allowed and a model that invents ``held 88%`` is still caught.
    """
    if isinstance(node, str):
        out.update(_NUMBER.findall(node))
    elif isinstance(node, Mapping):
        for value in node.values():
            _numbers_in_values(value, out)
    elif isinstance(node, (list, tuple)):
        for value in node:
            _numbers_in_values(value, out)


def allowed_numbers(facts: Mapping[str, Any]) -> set[str]:
    """Every numeric token the engine computed or already quoted, as it appears in a memo."""
    allowed: set[str] = set()
    for match in _matches(facts):
        allowed.add(fmt_pct(float(match.get("confidence", 0.0))))
    for owner in _owner_matches(facts):
        allowed.add(fmt_pct(float(owner.get("confidence", 0.0))))
    allowed.add(str(int(facts.get("owners_screened", 0))))
    allowed.add(str(len(_matches(facts))))
    allowed.add(str(len(_owner_matches(facts))))
    _numbers_in_values(facts, allowed)
    return allowed


def is_grounded(text: str, facts: Mapping[str, Any]) -> bool:
    """True when every number in ``text`` is one the engine actually computed."""
    allowed = allowed_numbers(facts)
    return all(token in allowed for token in _NUMBER.findall(text))


def build_memo(facts: Mapping[str, Any]) -> str:
    """Compose a grounded disposition memo from the engine facts (no model involved)."""
    subject = str(facts.get("subject", ""))
    band = str(facts.get("band", ""))
    recommendation = str(facts.get("recommendation", "")).replace("_", " ")
    lines: list[str] = [
        f"Screening disposition for {subject}.",
        f"Deterministic engine band: {band}. Proposed disposition: {recommendation}.",
    ]
    matches = _matches(facts)
    if matches:
        lines.append(
            f"Name screening returned {len(matches)} match(es) at or above the review band:"
        )
        for match in matches:
            confidence = fmt_pct(float(match.get("confidence", 0.0)))
            lines.append(
                f"  - {match.get('name', '')} against {match.get('list_id', '')} entry "
                f"{match.get('entry', '')} at confidence {confidence}."
            )
    else:
        lines.append("Name screening returned no match at or above the review band.")

    owners = int(facts.get("owners_screened", 0))
    owner_matches = _owner_matches(facts)
    if owners:
        lines.append(
            f"Beneficial ownership: {owners} resolved owner(s) screened; "
            f"{len(owner_matches)} carried a list or PEP match."
        )
        for owner in owner_matches:
            confidence = fmt_pct(float(owner.get("confidence", 0.0)))
            lines.append(
                f"  - owner {owner.get('name', '')} banded {owner.get('band', '')} "
                f"at confidence {confidence}."
            )

    media = facts.get("adverse_media") or ()
    if isinstance(media, Sequence) and media:
        lines.append("Adverse media (advisory only, not scored into the band):")
        for item in media:
            if isinstance(item, Mapping):
                lines.append(f"  - {item.get('headline', '')}.")

    guidance = str(facts.get("guidance", "")).strip()
    if guidance:
        lines.append(f"Applicable guidance: {guidance}")

    lines.append(
        "This disposition is a recommendation only. It requires human review and has been routed "
        "to the review console; the system never clears a match on its own."
    )
    return "\n".join(lines)
