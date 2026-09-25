"""API request/response schemas (Pydantic) mapped to/from the pure-domain models."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from ..domain.models import PartyKind, ScreeningRequest, ScreeningResult


class ScreenRequest(BaseModel):
    """A screening request. Only ``subject`` is required; the rest sharpen or widen the screen."""

    subject: str
    kind: str = PartyKind.ENTITY.value
    dob: str = ""
    identifiers: list[str] = []
    jurisdiction: str = ""
    #: The subject's UBO graph key at cdd-sow-research. Empty means "do not resolve ownership".
    subject_id: str = ""
    #: Payment-message fields (ISO 20022 element names or SWIFT tags) to extract parties from.
    message: dict[str, str] = {}
    #: Free-text context, carried into the audit summary, never scored into the band.
    context: str = ""

    def to_domain(self) -> ScreeningRequest:
        kind = PartyKind(self.kind) if self.kind in tuple(PartyKind) else PartyKind.UNKNOWN
        return ScreeningRequest.from_message(
            self.subject,
            self.message,
            kind=kind,
            dob=self.dob,
            identifiers=tuple(self.identifiers),
            jurisdiction=self.jurisdiction,
            subject_id=self.subject_id,
            context=self.context,
        )


class CitationModel(BaseModel):
    source_id: str
    title: str
    snippet: str = ""


class MatchModel(BaseModel):
    name: str
    list_id: str
    entry_id: str
    band: str
    confidence: float
    arithmetic: str


class PartyScreeningModel(BaseModel):
    party_name: str
    role: str
    band: str
    recommendation: str
    matches: list[MatchModel] = []


class ScreenResponse(BaseModel):
    subject: str
    band: str
    recommendation: str
    severity: str
    decision: str
    requires_human_review: bool
    owners_screened: int
    memo: str
    memo_grounded: bool
    #: Where the disposition WENT (rule R8): the human-review-console review id, or the local queue
    #: reference. Empty exactly when ``review_routing`` is not ``routed``.
    review_ref: str = ""
    #: What happened to the hand-off: routed, failed, off or not_required. ``failed`` means the
    #: disposition is NOT queued for review, and the console says so.
    review_routing: Literal["routed", "failed", "off", "not_required"] = "not_required"
    party_screenings: list[PartyScreeningModel] = []
    citations: list[CitationModel] = []
    flags: list[str] = []

    @classmethod
    def from_domain(
        cls,
        result: ScreeningResult,
        *,
        review_ref: str = "",
        review_routing: str = "not_required",
    ) -> ScreenResponse:
        return cls(
            subject=result.subject,
            band=result.band.value,
            recommendation=result.recommendation.value,
            severity=result.severity.value,
            decision=result.decision.value,
            requires_human_review=result.requires_human_review,
            owners_screened=result.owners_screened,
            memo=result.memo.text,
            memo_grounded=result.memo.grounded,
            review_ref=review_ref,
            review_routing=review_routing,  # type: ignore[arg-type]
            party_screenings=[
                PartyScreeningModel(
                    party_name=s.party.name,
                    role=s.party.role.value,
                    band=s.band.value,
                    recommendation=s.recommendation.value,
                    matches=[
                        MatchModel(
                            name=m.entry.name,
                            list_id=m.entry.list_id,
                            entry_id=m.entry.entry_id,
                            band=m.band.value,
                            confidence=m.confidence,
                            arithmetic=m.score.arithmetic,
                        )
                        for m in s.matches
                    ],
                )
                for s in result.party_screenings
            ],
            citations=[
                CitationModel(source_id=c.source_id, title=c.title, snippet=c.snippet)
                for c in result.citations
            ],
            flags=list(result.flags),
        )


class HealthResponse(BaseModel):
    status: str
    profile: str
    region: str
    #: What the UI's model pill states before any answer: where the runtime sits and which model
    #: the bound generator calls. Both are read off the service because the browser cannot know
    #: either. Once a request is answered, the pill shows that response's ``X-Answered-By``.
    runtime: str = "local"  # "gcp" | "local"
    generator_model: str = "deterministic-offline-stub"
