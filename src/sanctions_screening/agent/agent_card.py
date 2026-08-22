"""The A2A discovery card: what this agent can be asked to do, in one machine-readable place.

Served at ``/.well-known/agent-card.json`` and registrable with Hrz3 (rule R4). The card is
built from the SAME tool table the runtime binds, so an agent cannot advertise a skill it does
not implement or implement one it never advertises; ``tests/unit/test_agent_surface.py`` fails
the build when the two disagree.

Pure: domain types and stdlib only, no ADK and no cloud SDK, so the card can be generated and
inspected offline.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from hex_service_kit.serialization import to_jsonable

from ..config import Settings

_CARD_VERSION = "0.1.0"


@dataclass(frozen=True, slots=True)
class AgentSkill:
    """One advertised capability. ``id`` is the tool function's name, never a prose label."""

    id: str
    name: str
    description: str


@dataclass(frozen=True, slots=True)
class AgentCard:
    """The minimal A2A discovery document a peer agent or the registry reads."""

    name: str
    description: str
    url: str
    version: str = _CARD_VERSION
    provider: str = "sanctions-screening"
    skills: tuple[AgentSkill, ...] = field(default_factory=tuple)


SKILLS: tuple[AgentSkill, ...] = (
    AgentSkill(
        id="screen_name",
        name="Name screening",
        description=(
            "Screen one party name against the sanctions and PEP list packs with the "
            "deterministic fuzzy-match engine, screen the subject's beneficial owners from "
            "Doc1, draft a grounded disposition memo, and ROUTE the disposition to human review "
            "(rule R8). The confidence band is computed by pure stdlib code, never by a model."
        ),
    ),
    AgentSkill(
        id="screen_payment_message",
        name="Payment-message screening",
        description=(
            "Extract every party from an ISO 20022 or SWIFT payment message (debtor, creditor "
            "and their ultimate parties), screen each against the lists, and route the combined "
            "disposition for human review. Field extraction is deterministic and cited."
        ),
    ),
    AgentSkill(
        id="list_disposition_queue",
        name="Disposition queue",
        description=(
            "List the screening dispositions currently queued for human review on the offline "
            "outbox, with each item's case reference and severity, so a reviewer can see what "
            "is pending. Payloads are redacted before they are returned."
        ),
    ),
    AgentSkill(
        id="verify_audit_trail",
        name="Audit-trail verification",
        description=(
            "Re-derive the hash chain over the stored audit trail and cross-check the external "
            "head anchor, returning an honest verdict: intact, or the first record that broke "
            "the chain, or the anchor disagreement that exposes a truncated tail."
        ),
    ),
)

#: Joined from short pieces, each carrying at most one template variable, so a longer
#: ``friendly_name`` cannot push a line past the formatter's limit in the rendered repo while
#: the template itself still looks fine. The vertical's own prose belongs in ``README.md``;
#: the card says what the agent IS and what it guarantees.
_DESCRIPTION = " ".join(
    (
        "Sanctions Screening Copilot",
        "(G2).",
        "Deterministic decision, cited output, redact-before-audit, and every",
        "consequential result routed to a human reviewer.",
    )
)


def build_agent_card(settings: Settings | None = None) -> AgentCard:
    """Construct the A2A card for this agent in the configured deployment."""
    resolved = settings or Settings.load()
    return AgentCard(
        name="sanctions-screening",
        description=_DESCRIPTION,
        url=_resolve_url(resolved),
        skills=SKILLS,
    )


def agent_card_document(settings: Settings | None = None) -> dict[str, Any]:
    """The JSON-safe body served at ``/.well-known/agent-card.json``."""
    document = to_jsonable(build_agent_card(settings))
    if not isinstance(document, dict):  # pragma: no cover - dataclasses serialise to objects
        raise TypeError("an agent card must serialise to a JSON object")
    return document


def _resolve_url(settings: Settings) -> str:
    """Best-effort public URL for the card, region-qualified so residency is visible on it."""
    return f"https://sanctions-screening.{settings.region}.internal.example/a2a"
