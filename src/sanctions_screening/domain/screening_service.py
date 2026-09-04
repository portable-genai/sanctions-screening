"""The screening orchestrator: deterministic bands, consumed ownership, supervised narration, R8.

The consequential decisions (the match confidence, the band, the recommendation, the effective
ownership percentages) are PURE engine output; the model narrates the memo and produces no number.
The pipeline, in order: parse the parties, screen each against the list packs, consume
cdd-sow-research's resolved ownership graph and screen each beneficial owner, gather advisory
adverse media, band the whole subject, draft the memo under groundedness validation, redact, and
write the audit record.

Every disposition is consequential: ``requires_human_review`` is ALWAYS True and the caller routes
the result to human-review-console (rule R8). The system never clears a match on its own.
"""

from __future__ import annotations

from typing import Any

from pii_kit import redact

from ..ports.adverse_media import AdverseMediaPort
from ..ports.audit import AuditSinkPort
from ..ports.narration import NarrationPort
from ..ports.observability import ObservabilityTracerPort
from ..ports.ownership_graph import OwnershipGraphPort
from .kernel import AuditEvent, Citation, Decision, Severity, utcnow
from .listpacks import GuidanceNote
from .match_engine import MatchEngine, recommendation_for
from .memo import build_memo, is_grounded
from .message_fields import extract_parties
from .models import (
    AdverseMediaFinding,
    DispositionMemo,
    ListEntry,
    MatchBand,
    OwnershipGraph,
    PartyKind,
    PartyRole,
    PartyScreening,
    Recommendation,
    ScreenableParty,
    ScreeningRequest,
    ScreeningResult,
    worst_band,
)
from .pii import PII_PATTERNS
from .policy import MatchPolicy

#: One span per screened subject. Structural attributes only: see
#: :meth:`ScreeningService.screen`.
_SCREEN_SPAN = "sanctions.screen"

#: Band to severity, so the shared review payload demands dual control on a confirmed match.
_BAND_SEVERITY: dict[MatchBand, Severity] = {
    MatchBand.CONFIRMED: Severity.CRITICAL,
    MatchBand.STRONG: Severity.HIGH,
    MatchBand.POSSIBLE: Severity.MEDIUM,
    MatchBand.WEAK: Severity.LOW,
    MatchBand.CLEAR: Severity.LOW,
}


def _redacted(node: Any) -> Any:
    """Mask personal data in every string of a nested structure, however deep.

    The memo facts are the model's whole input, and they are assembled from two sources that are
    both free text: the SUBJECT the caller typed (a screen of a natural person carries the name
    and the national id in that field) and the beneficial-owner names cdd-sow-research resolved, who
    are
    natural persons named by another service and never the caller's own text. Walking the whole
    structure rather than the two fields somebody remembers means a third source added later is
    covered the day it is added.
    """
    if isinstance(node, str):
        return redact(node, PII_PATTERNS)
    if isinstance(node, dict):
        return {key: _redacted(value) for key, value in node.items()}
    if isinstance(node, list):
        return [_redacted(value) for value in node]
    if isinstance(node, tuple):
        return tuple(_redacted(value) for value in node)
    return node


def _redacted_citations(citations: tuple[Citation, ...]) -> tuple[Citation, ...]:
    """Mask every field of every citation. The WORM boundary, held by construction.

    Today's citations are list-pack and guidance locators with nothing to mask, and that is
    exactly why this is unconditional: no sink can tell an engine-built citation from one cut out
    of caller text by inspection, redacting text that carries no identifier is a no-op, and
    deciding per producer is how one producer ends up forgetting.
    """
    return tuple(
        Citation(
            source_id=redact(c.source_id, PII_PATTERNS),
            title=redact(c.title, PII_PATTERNS),
            snippet=redact(c.snippet, PII_PATTERNS),
        )
        for c in citations
    )


class ScreeningService:
    """Screen a subject and its parties, consume ownership, narrate, and route for review."""

    def __init__(
        self,
        audit: AuditSinkPort,
        ownership: OwnershipGraphPort,
        adverse_media: AdverseMediaPort,
        narration: NarrationPort,
        *,
        tracer: ObservabilityTracerPort,
        engine: MatchEngine,
        list_entries: tuple[ListEntry, ...],
        guidance: tuple[GuidanceNote, ...],
        policy: MatchPolicy,
    ) -> None:
        self._audit = audit
        self._ownership = ownership
        self._adverse_media = adverse_media
        self._narration = narration
        self._tracer = tracer
        self._engine = engine
        self._list_entries = list_entries
        self._guidance = guidance
        self._policy = policy

    # ------------------------------------------------------------------ pipeline

    def screen(
        self, request: ScreeningRequest, *, actor: str, tenant: str = "", as_of: str = ""
    ) -> ScreeningResult:
        """Screen one subject end to end, inside one span.

        ``tenant`` is the VERIFIED principal's, never a value from a request body, and it scopes
        the ONE read this service makes of stored data: cdd-sow-research's ownership graph, which
        the caller
        names by a client-supplied key and whose beneficial owners are natural persons. An empty
        tenant resolves no graph rather than every graph.

        The span's attributes are STRUCTURAL only: the action, the actor and the party kind,
        never the subject name, an identifier, the analyst's free-text context or the drafted
        memo. A trace backend is not the WORM audit trail: it has no redaction stage, a wider
        read audience and no retention rule written against a regulator's requirement, so
        anything content-shaped that reaches a span has left the boundary the redact calls
        exist to hold, and left it silently.
        """
        with self._tracer.span(
            _SCREEN_SPAN,
            action="screen",
            actor=actor,
            kind=request.kind.value,
        ):
            parties = self._parties(request)
            screenings = [self._engine.screen_party(p, self._list_entries) for p in parties]

            ownership, owner_screenings, flags = self._screen_owners(request, as_of, tenant)
            screenings.extend(owner_screenings)
            owners_screened = len(ownership.beneficial_owners) if ownership is not None else 0

            media = self._adverse(request.subject, request.kind)

            overall_band = worst_band(tuple(s.band for s in screenings))
            recommendation = recommendation_for(overall_band)
            severity = _BAND_SEVERITY[overall_band]

            memo = self._draft_memo(
                request.subject, overall_band, recommendation, screenings, owners_screened, media
            )

            base = (
                f"{request.subject}: screened {overall_band.value} / {recommendation.value}; "
                f"{owners_screened} owner(s) screened"
            )
            # The analyst's free-text context travels on the summary so a checker sees what was
            # typed; it is masked at every boundary (this audit write, and the review payload),
            # so a raw identifier a caller pasted in never reaches the WORM record or the
            # console.
            summary = f"{base} :: {request.context}" if request.context.strip() else base
            citations = self._citations(screenings, media, memo)

            self._audit.record(
                AuditEvent(
                    action="screen",
                    actor=actor,
                    decision=Decision.ESCALATED,
                    severity=severity,
                    redacted_summary=redact(summary, PII_PATTERNS),
                    citations=_redacted_citations(citations),
                    timestamp=utcnow(),
                )
            )

            return ScreeningResult(
                subject=request.subject,
                party_screenings=tuple(screenings),
                owners_screened=owners_screened,
                ownership=ownership,
                adverse_media=media,
                band=overall_band,
                recommendation=recommendation,
                memo=memo,
                severity=severity,
                decision=Decision.ESCALATED,
                summary=summary,
                requires_human_review=True,
                citations=citations,
                as_of=as_of,
                flags=tuple(flags),
            )

    # ------------------------------------------------------------------ steps

    def _parties(self, request: ScreeningRequest) -> list[ScreenableParty]:
        subject = ScreenableParty(
            party_id="subject",
            name=request.subject,
            role=PartyRole.SUBJECT,
            kind=request.kind,
            dob=request.dob,
            identifiers=request.identifiers,
            jurisdiction=request.jurisdiction,
            source_ref="subject",
        )
        return [subject, *extract_parties(request.message)]

    def _screen_owners(
        self, request: ScreeningRequest, as_of: str, tenant: str
    ) -> tuple[OwnershipGraph | None, list[PartyScreening], list[str]]:
        """Resolve and screen ``tenant``'s beneficial owners, degrading when unreachable.

        A confirmed refusal (the on-prem placeholder) is re-raised: an on-prem deployment must
        wire its own source rather than silently screen no owners. A transport failure on a
        configured source degrades with a flag, because serving the name screening without the
        ownership enrichment is serving LESS, not serving less-verified.

        A graph that belongs to somebody else degrades the SAME way, with the same flag: the
        caller is told the ownership enrichment did not happen and is told nothing about whose
        graph exists behind the key they named. Refusing the enrichment is not refusing the
        request, so the name screening still runs and still bands.
        """
        if not request.subject_id:
            return None, [], []
        try:
            graph = self._ownership.resolve(
                request.subject_id, request.subject, tenant=tenant, as_of=as_of
            )
        except NotImplementedError:
            raise
        except Exception:
            return None, [], ["ownership_unresolved"]
        owner_screenings: list[PartyScreening] = []
        for owner in graph.beneficial_owners:
            party = ScreenableParty(
                party_id=owner.node_id,
                name=owner.name,
                role=PartyRole.BENEFICIAL_OWNER,
                kind=PartyKind.INDIVIDUAL,
                jurisdiction=owner.jurisdiction,
                source_ref=owner.node_id,
            )
            owner_screenings.append(self._engine.screen_party(party, self._list_entries))
        flags = ["ownership_truncated"] if graph.truncated else []
        return graph, owner_screenings, flags

    def _adverse(self, subject: str, kind: PartyKind) -> tuple[AdverseMediaFinding, ...]:
        """Adverse media is advisory: a failure drops the enrichment, it never changes a band."""
        try:
            return self._adverse_media.search(subject, kind=kind)
        except Exception:
            return ()

    def _draft_memo(
        self,
        subject: str,
        band: MatchBand,
        recommendation: Recommendation,
        screenings: list[PartyScreening],
        owners_screened: int,
        media: tuple[AdverseMediaFinding, ...],
    ) -> DispositionMemo:
        facts = self._memo_facts(subject, band, recommendation, screenings, owners_screened, media)
        # Masked HERE, where the facts cross out to the model, so the drafted memo, the returned
        # result and anything a surface renders from them are covered at one boundary rather than
        # three. P-04 is about what the model READS as much as about what the record keeps.
        facts = _redacted(facts)
        citations = self._memo_citations(screenings, media)
        try:
            draft = self._narration.draft_memo(facts)
        except Exception:
            draft = ""
        if draft.strip() and is_grounded(draft, facts):
            return DispositionMemo(text=draft, grounded=True, citations=citations)
        # Discard the draft (a model that invented a number, or a refusing adapter) and fall back
        # to the deterministic memo, which is grounded by construction.
        return DispositionMemo(text=build_memo(facts), grounded=False, citations=citations)

    # ------------------------------------------------------------------ helpers

    def _memo_facts(
        self,
        subject: str,
        band: MatchBand,
        recommendation: Recommendation,
        screenings: list[PartyScreening],
        owners_screened: int,
        media: tuple[AdverseMediaFinding, ...],
    ) -> dict[str, Any]:
        matches: list[dict[str, Any]] = []
        owner_matches: list[dict[str, Any]] = []
        for screening in screenings:
            if not screening.matches:
                continue
            best = screening.matches[0]
            row = {
                "name": screening.party.name,
                "list_id": best.entry.list_id,
                "entry": best.entry.entry_id,
                "confidence": best.confidence,
            }
            if screening.party.role is PartyRole.BENEFICIAL_OWNER:
                owner_matches.append({**row, "band": screening.band.value})
            else:
                matches.append(row)
        return {
            "subject": subject,
            "band": band.value,
            "recommendation": recommendation.value,
            "matches": matches,
            "owner_matches": owner_matches,
            "owners_screened": owners_screened,
            "adverse_media": [{"headline": f.headline} for f in media],
            "guidance": self._guidance_text(),
        }

    def _guidance_text(self) -> str:
        return self._guidance[0].text if self._guidance else ""

    def _memo_citations(
        self, screenings: list[PartyScreening], media: tuple[AdverseMediaFinding, ...]
    ) -> tuple[Citation, ...]:
        citations: list[Citation] = []
        for screening in screenings:
            for match in screening.matches:
                citations.extend(match.citations)
        citations.extend(f.citation for f in media)
        if self._guidance:
            citations.append(self._guidance[0].citation)
        return _dedupe(citations)

    def _citations(
        self,
        screenings: list[PartyScreening],
        media: tuple[AdverseMediaFinding, ...],
        memo: DispositionMemo,
    ) -> tuple[Citation, ...]:
        citations = list(self._memo_citations(screenings, media))
        # Always cite the run itself, so even a clean screen carries provenance for what was done.
        citations.append(
            Citation(
                source_id="run:screening",
                title="Lists screened",
                snippet=f"{len(self._list_entries)} reference entries",
            )
        )
        return _dedupe(citations + list(memo.citations))


def _dedupe(citations: list[Citation]) -> tuple[Citation, ...]:
    seen: set[str] = set()
    out: list[Citation] = []
    for citation in citations:
        if citation.source_id in seen:
            continue
        seen.add(citation.source_id)
        out.append(citation)
    return tuple(out)
