"""Vertical artifact models: the request and result types of sanctions screening.

The artifacts THIS vertical produces, as opposed to the vertical-neutral machinery in
``kernel.py``. Every consequential number on these types (a match confidence, an effective
ownership percentage, a band) is computed by pure stdlib engine code and never by a model; the
model narrates the disposition memo and nothing else. Every claim that leaves the service carries
a ``Citation``.

A fork building a different vertical rewrites this module and keeps ``kernel.py`` untouched.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

from hex_service_kit.enums import LenientStrEnum

from .kernel import Citation, Decision, Severity


class PartyRole(LenientStrEnum):
    """Where a screenable party came from in the request."""

    SUBJECT = "subject"
    DEBTOR = "debtor"
    CREDITOR = "creditor"
    ULTIMATE_DEBTOR = "ultimate_debtor"
    ULTIMATE_CREDITOR = "ultimate_creditor"
    BENEFICIAL_OWNER = "beneficial_owner"


class PartyKind(LenientStrEnum):
    """The kind of party a name denotes, which changes how it is matched."""

    INDIVIDUAL = "individual"
    ENTITY = "entity"
    VESSEL = "vessel"
    UNKNOWN = "unknown"


class MatchBand(LenientStrEnum):
    """The match-confidence band a name pair falls into. Ordered by :data:`_BAND_ORDER`."""

    CLEAR = "clear"
    WEAK = "weak"
    POSSIBLE = "possible"
    STRONG = "strong"
    CONFIRMED = "confirmed"


class Recommendation(LenientStrEnum):
    """The disposition the engine proposes. Never auto-executed: a human always decides."""

    FALSE_POSITIVE = "false_positive"
    NEEDS_INFO = "needs_info"
    TRUE_MATCH = "true_match"


#: Bands from least to most severe, so "the worst across parties" is a max over this order.
_BAND_ORDER: tuple[MatchBand, ...] = (
    MatchBand.CLEAR,
    MatchBand.WEAK,
    MatchBand.POSSIBLE,
    MatchBand.STRONG,
    MatchBand.CONFIRMED,
)


def band_rank(band: MatchBand) -> int:
    """The ordinal of a band, so callers compare severity without re-encoding the order."""
    return _BAND_ORDER.index(band)


def worst_band(bands: tuple[MatchBand, ...]) -> MatchBand:
    """The most severe band in a set, or ``CLEAR`` when the set is empty."""
    return max(bands, key=band_rank) if bands else MatchBand.CLEAR


@dataclass(frozen=True, slots=True)
class ScreenableParty:
    """One party to be screened: a name plus the attributes that sharpen a match."""

    party_id: str
    name: str
    role: PartyRole
    kind: PartyKind = PartyKind.UNKNOWN
    dob: str = ""
    identifiers: tuple[str, ...] = ()
    jurisdiction: str = ""
    #: Where the party came from (a message field id, or a graph node id): traceable provenance.
    source_ref: str = ""


@dataclass(frozen=True, slots=True)
class ListEntry:
    """One reference entry from a sanctions or PEP list pack (the data screened against)."""

    list_id: str
    entry_id: str
    name: str
    kind: PartyKind
    aliases: tuple[str, ...] = ()
    dob: str = ""
    identifiers: tuple[str, ...] = ()
    program: str = ""
    citation: Citation | None = None


@dataclass(frozen=True, slots=True)
class NameScore:
    """The deterministic arithmetic behind one confidence figure, kept so a human can audit it."""

    normalized_query: str
    normalized_candidate: str
    token_score: float
    name_part_score: float
    dob_score: float
    id_score: float
    confidence: float
    arithmetic: str


@dataclass(frozen=True, slots=True)
class PartyMatch:
    """A party matched against one list entry, with its band and the arithmetic that set it."""

    party: ScreenableParty
    entry: ListEntry
    band: MatchBand
    confidence: float
    score: NameScore
    citations: tuple[Citation, ...] = ()


@dataclass(frozen=True, slots=True)
class PartyScreening:
    """The screening of one party against the whole list set: ranked matches, band, proposal."""

    party: ScreenableParty
    matches: tuple[PartyMatch, ...]
    band: MatchBand
    recommendation: Recommendation


@dataclass(frozen=True, slots=True)
class OwnershipNode:
    """A node in the beneficial-ownership graph consumed from cdd-sow-research (subset of its
    contract).
    """

    node_id: str
    name: str
    kind: str
    jurisdiction: str = ""
    is_pep: bool = False
    depth: int = 0


@dataclass(frozen=True, slots=True)
class OwnershipEdge:
    """An ownership or control edge. ``pct`` is 0..100, never a 0..1 fraction (cdd-sow-research
    contract).
    """

    source_id: str
    target_id: str
    kind: str
    pct: float = 0.0


@dataclass(frozen=True, slots=True)
class BeneficialOwner:
    """A natural person at or above the ownership threshold, per cdd-sow-research's resolution."""

    node_id: str
    name: str
    kind: str
    jurisdiction: str = ""
    is_pep: bool = False
    effective_pct: float = 0.0
    meets_threshold: bool = False


@dataclass(frozen=True, slots=True)
class OwnershipGraph:
    """The resolved ownership graph for a subject, read from cdd-sow-research's frozen A2A contract.

    ``truncated`` or a non-empty ``unresolved_ids`` means the percentages are a FLOOR: the
    structure is partial, and a consumer that presents it as complete is misreporting it.
    """

    subject_id: str
    subject_name: str
    root_id: str
    #: The tenant that OWNS this graph, as published on cdd-sow-research's contract. It is the data
    #: tag
    #: object-level authorization is derived from: a UBO graph key is a name, not an
    #: entitlement, and the beneficial owners behind it are natural persons. Empty means the
    #: source did not say, so no principal may read it.
    tenant: str = ""
    nodes: tuple[OwnershipNode, ...] = ()
    edges: tuple[OwnershipEdge, ...] = ()
    beneficial_owners: tuple[BeneficialOwner, ...] = ()
    truncated: bool = False
    unresolved_ids: tuple[str, ...] = ()
    opacity_score: float = 0.0
    ownership_threshold_pct: float = 25.0
    as_of: str = ""


@dataclass(frozen=True, slots=True)
class AdverseMediaFinding:
    """One adverse-media hit. Advisory to the memo, never to the band (the plan's rule)."""

    party_name: str
    headline: str
    severity: Severity
    snippet: str
    citation: Citation


@dataclass(frozen=True, slots=True)
class DispositionMemo:
    """The narrated disposition memo. ``grounded`` is False when the drafter was discarded."""

    text: str
    grounded: bool
    citations: tuple[Citation, ...] = ()


@dataclass(frozen=True, slots=True)
class ScreeningRequest:
    """One screening request: a subject name and the context that sharpens or widens it."""

    subject: str
    kind: PartyKind = PartyKind.ENTITY
    dob: str = ""
    identifiers: tuple[str, ...] = ()
    jurisdiction: str = ""
    #: The subject's UBO graph key at cdd-sow-research. Empty means "do not resolve ownership".
    subject_id: str = ""
    #: A parsed payment message as ordered field pairs (ISO 20022 / SWIFT). Empty means the
    #: subject name is screened on its own.
    message: tuple[tuple[str, str], ...] = ()
    #: Free-text context a caller may attach; carried into the audit summary, never scored.
    context: str = ""

    @classmethod
    def from_message(
        cls, subject: str, message: Mapping[str, str], **kwargs: object
    ) -> ScreeningRequest:
        """Build a request from a mapping of message fields, preserving a stable field order."""
        pairs = tuple((str(k), str(v)) for k, v in message.items())
        return cls(subject=subject, message=pairs, **kwargs)  # type: ignore[arg-type]


@dataclass(frozen=True, slots=True)
class ScreeningResult:
    """The screening disposition: matches, ownership coverage, memo, and the review it routes to.

    The kernel-compatible fields (``subject``, ``severity``, ``decision``, ``summary``,
    ``requires_human_review``, ``citations``) let the shared audit, review-payload and R8 routing
    machinery consume a screening result unchanged. ``requires_human_review`` is ALWAYS True: the
    system never clears a match on its own, so every disposition, including a proposed clear,
    routes to a human.
    """

    subject: str
    party_screenings: tuple[PartyScreening, ...]
    owners_screened: int
    ownership: OwnershipGraph | None
    adverse_media: tuple[AdverseMediaFinding, ...]
    band: MatchBand
    recommendation: Recommendation
    memo: DispositionMemo
    severity: Severity
    decision: Decision
    summary: str
    requires_human_review: bool
    citations: tuple[Citation, ...] = ()
    as_of: str = ""
    flags: tuple[str, ...] = field(default_factory=tuple)
