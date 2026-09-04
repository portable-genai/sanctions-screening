"""ONE canonical request per port, shared by the structural and behavioural contract suites.

Parity means the same request through every implementation, so the request needs a single home.
Each :class:`PortCase` answers three questions about one port:

* ``invoke``   : what a single canonical call to this port looks like;
* ``answered`` : what it means for the OFFLINE family to have actually answered (a port that
  returns ``None`` and records nothing has not answered, it has merely not raised);
* ``managed_refusal`` : how the MANAGED family fails when nothing is reachable. Never a silent
  success: either it refuses because it is unconfigured, or its lazy SDK import fails.

Adding a port means adding a case here; ``test_port_parity.py`` fails the build if this table and
the port map ever disagree.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from agent_eval_kit import EvalReport
from hex_service_kit.identity import IdentityError, Principal, RequestContext
from hex_service_kit.observability import TokenUsage

from sanctions_screening.adapters.local.ownership_graph import FIXTURE_TENANT
from sanctions_screening.domain.kernel import (
    AuditEvent,
    Citation,
    Decision,
    Severity,
)
from sanctions_screening.domain.models import (
    DispositionMemo,
    MatchBand,
    OwnershipGraph,
    Recommendation,
    ScreeningResult,
)

from tests.fixtures import sample_cases

#: The audit record every audit-port implementation is handed. Already redacted, as required.
CANONICAL_EVENT = AuditEvent(
    action="screen",
    actor=sample_cases.ACTOR,
    decision=Decision.ESCALATED,
    severity=Severity.CRITICAL,
    redacted_summary="Volkov Metals OJSC (FICTIONAL): screened confirmed / true_match",
    citations=(Citation(source_id="list:UN:UN-1001", title="UN listing UN-1001", snippet=""),),
)

#: The screening disposition every review-router implementation is handed (rule R8's payload).
CANONICAL_RESULT = ScreeningResult(
    subject=sample_cases.CONFIRMED_CASE.subject,
    party_screenings=(),
    owners_screened=0,
    ownership=None,
    adverse_media=(),
    band=MatchBand.CONFIRMED,
    recommendation=Recommendation.TRUE_MATCH,
    memo=DispositionMemo(text="Confirmed match; routed for human review.", grounded=True),
    severity=Severity.CRITICAL,
    decision=Decision.ESCALATED,
    summary=f"{sample_cases.CONFIRMED_CASE.subject}: screened confirmed / true_match",
    requires_human_review=True,
    citations=(Citation(source_id="list:UN:UN-1001", title="UN listing UN-1001", snippet=""),),
)

#: The inbound transport context every identity implementation is handed.
CANONICAL_CONTEXT = RequestContext(headers={"x-dev-persona": "auditor"})


@dataclass(frozen=True, slots=True)
class PortCase:
    """One port's canonical call plus the two verdicts the parity suites need."""

    invoke: Callable[[Any], Any]
    answered: Callable[[Any, Any], bool]
    managed_refusal: tuple[type[BaseException], ...]
    detail: str


def _audit_invoke(adapter: Any) -> Any:
    return adapter.record(CANONICAL_EVENT)


def _audit_answered(adapter: Any, _result: Any) -> bool:
    stored = adapter.log.read_all()
    return bool(stored) and stored[-1]["actor"] == sample_cases.ACTOR and adapter.verify().ok


def _identity_invoke(adapter: Any) -> Any:
    return adapter.resolve(CANONICAL_CONTEXT)


def _identity_answered(_adapter: Any, result: Any) -> bool:
    return isinstance(result, Principal) and bool(result.actor)


def _review_invoke(adapter: Any) -> Any:
    return adapter.route(CANONICAL_RESULT, maker=sample_cases.ACTOR, tenant=sample_cases.TENANT)


def _review_answered(adapter: Any, result: Any) -> bool:
    return bool(result) and len(adapter.outbox.pending()) == 1


def _ownership_invoke(adapter: Any) -> Any:
    return adapter.resolve("acme", sample_cases.CONFIRMED_CASE.subject, tenant=FIXTURE_TENANT)


def _ownership_answered(_adapter: Any, result: Any) -> bool:
    return isinstance(result, OwnershipGraph) and len(result.beneficial_owners) >= 1


def _adverse_invoke(adapter: Any) -> Any:
    return adapter.search("Dmitri Volkov (FICTIONAL)")


def _adverse_answered(_adapter: Any, result: Any) -> bool:
    return isinstance(result, tuple) and len(result) >= 1


def _narration_invoke(adapter: Any) -> Any:
    return adapter.draft_memo({"subject": "x", "matches": [], "owners_screened": 0})


def _narration_answered(_adapter: Any, result: Any) -> bool:
    return isinstance(result, str) and bool(result.strip())


def _tracer_invoke(adapter: Any) -> Any:
    with adapter.span("canonical.unit", action="canonical"):
        adapter.record_token_usage(TokenUsage(input_tokens=7, output_tokens=2), "canonical-model")
    return True


def _tracer_answered(adapter: Any, result: Any) -> bool:
    return bool(result)


def _evaluation_invoke(adapter: Any) -> Any:
    return adapter.evaluate("eval/datasets/canonical.jsonl")


def _evaluation_answered(adapter: Any, result: Any) -> bool:
    return isinstance(result, EvalReport) and result.dataset.endswith("canonical.jsonl")


CANONICAL_CALLS: dict[str, PortCase] = {
    "audit": PortCase(
        invoke=_audit_invoke,
        answered=_audit_answered,
        managed_refusal=(ImportError,),
        detail="write one already-redacted WORM record",
    ),
    "identity": PortCase(
        invoke=_identity_invoke,
        answered=_identity_answered,
        managed_refusal=(IdentityError,),
        detail="resolve a verified principal from transport context",
    ),
    "review_router": PortCase(
        invoke=_review_invoke,
        answered=_review_answered,
        # Rule R8: with no console configured the managed router must refuse, not swallow.
        managed_refusal=(RuntimeError,),
        detail="route one screening disposition to human review",
    ),
    "ownership_graph": PortCase(
        invoke=_ownership_invoke,
        answered=_ownership_answered,
        # With no cdd-sow-research URL configured the managed adapter refuses rather than inventing
        # a graph.
        managed_refusal=(RuntimeError,),
        detail="resolve one subject's beneficial-ownership graph",
    ),
    "adverse_media": PortCase(
        invoke=_adverse_invoke,
        answered=_adverse_answered,
        # The lazy managed grounded-search import is the first thing the adapter does.
        managed_refusal=(ImportError,),
        detail="return severity-ordered adverse-media findings",
    ),
    "narration": PortCase(
        invoke=_narration_invoke,
        answered=_narration_answered,
        # The lazy managed model import is the first thing the adapter does.
        managed_refusal=(ImportError,),
        detail="draft a disposition memo from the engine facts",
    ),
    "tracer": PortCase(
        invoke=_tracer_invoke,
        answered=_tracer_answered,
        # NOTHING. Tracing is not essential to correctness, so the managed adapter must not refuse
        # offline either: with no SDK it degrades to a no-op and the traced body still runs. An
        # adapter that raised here would take a request down over a diagnostic.
        managed_refusal=(),
        detail="open one span and report the cost of a model call",
    ),
    "evaluation": PortCase(
        invoke=_evaluation_invoke,
        answered=_evaluation_answered,
        # The managed gate reaches model-quality-gate over HTTP, which is unreachable offline.
        managed_refusal=(Exception,),
        detail="score one golden dataset through the promotion authority",
    ),
}
