"""Tool functions an agent runtime calls: thin, side-effect-honest wrappers on the service.

Design rules, in the order they matter:

* **No business logic here.** The screening service decides HOW; the model only decides WHICH
  tool to call. A rule that lives in a tool wrapper is a rule the CLI and the API do not have.
* **Rule R8 applies on this path too.** Every screening disposition is ROUTED from inside the
  tool, in the same call that produced it, because every disposition is consequential.
* **Import-safe without a runtime.** ``google.adk`` is imported lazily inside
  :func:`build_function_tools`, so these callables are importable, testable and runnable with no
  ADK and no cloud SDK installed.
* **Typed and documented.** A runtime derives each tool's name, description and JSON parameter
  schema from the signature and the docstring, so both are part of the contract.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from hex_service_kit.serialization import to_jsonable
from pii_kit import redact

from ..config import Container, Settings, build_container
from ..domain.models import PartyKind, ScreeningRequest
from ..domain.pii import PII_PATTERNS
from ..service_factory import build_screening_service

if TYPE_CHECKING:  # pragma: no cover - typing only, never imported at runtime
    from google.adk.tools import FunctionTool

#: The identity a tool call is attributed to when the runtime propagates none. It names the
#: SERVICE, not a person, so an unattributed action is never mistaken for a human's.
DEFAULT_ACTOR = "sanctions-screening-agent"


def _container(settings: Settings | None) -> Container:
    return build_container(settings)


def _redacted(node: Any) -> Any:
    """Mask personal data in every string of a tool result, however deeply it is nested."""
    if isinstance(node, str):
        return redact(node, PII_PATTERNS)
    if isinstance(node, dict):
        return {key: _redacted(value) for key, value in node.items()}
    if isinstance(node, list):
        return [_redacted(value) for value in node]
    return node


def _screen(
    request: ScreeningRequest, actor: str, tenant: str, settings: Settings | None
) -> dict[str, Any]:
    container = _container(settings)
    service = build_screening_service(container)
    scope = tenant or container.settings.tenant
    result = service.screen(request, actor=actor, tenant=scope)
    review_ref = container.review_router.route(result, maker=actor, tenant=tenant)
    payload = _redacted(to_jsonable(result))
    if not isinstance(payload, dict):  # pragma: no cover - dataclasses serialise to objects
        raise TypeError("a screening result must serialise to a JSON object")
    payload["review_ref"] = review_ref
    return payload


def screen_name(
    subject: str,
    kind: str = PartyKind.ENTITY.value,
    subject_id: str = "",
    actor: str = DEFAULT_ACTOR,
    tenant: str = "",
    settings: Settings | None = None,
) -> dict[str, Any]:
    """Screen one party name against the sanctions and PEP lists and route the disposition.

    Scores the name against every list entry with the deterministic match engine, optionally
    resolves and screens the subject's beneficial owners from cdd-sow-research, drafts a grounded
    disposition
    memo, and routes the disposition to human review (rule R8).

    Args:
      subject: The party name to screen.
      kind: ``individual``, ``entity``, ``vessel`` or ``unknown``.
      subject_id: The subject's UBO graph key at cdd-sow-research; empty skips ownership resolution.
      actor: The verified identity this call is attributed to.
      tenant: Tenant partition asserted on the outbound review.

    Returns:
      A JSON-safe result with every string masked for personal data (P-04), plus ``review_ref``:
      where the disposition WENT.
    """
    resolved_kind = PartyKind(kind) if kind in tuple(PartyKind) else PartyKind.UNKNOWN
    request = ScreeningRequest(subject=subject, kind=resolved_kind, subject_id=subject_id)
    return _screen(request, actor, tenant, settings)


def screen_payment_message(
    subject: str,
    message: dict[str, str],
    actor: str = DEFAULT_ACTOR,
    tenant: str = "",
    settings: Settings | None = None,
) -> dict[str, Any]:
    """Screen every party extracted from a payment message (ISO 20022 / SWIFT), and route it.

    Args:
      subject: The primary subject name (usually the instructing customer).
      message: Message fields keyed by ISO 20022 element name or SWIFT tag.
      actor: The verified identity this call is attributed to.
      tenant: Tenant partition asserted on the outbound review.

    Returns:
      A JSON-safe result masked for personal data, plus ``review_ref``.
    """
    request = ScreeningRequest.from_message(subject, message)
    return _screen(request, actor, tenant, settings)


def list_disposition_queue(settings: Settings | None = None) -> dict[str, Any]:
    """List the dispositions currently queued for human review on the offline outbox.

    Returns:
      A dict with the pending count and, for each item, its case reference and severity. The
      managed router submits to human-review-console directly and has no local queue; there this
      reports zero.
    """
    router = _container(settings).review_router
    outbox = getattr(router, "outbox", None)
    if outbox is None:
        return {"pending": 0, "items": [], "detail": "no local queue for this profile"}
    items = [
        {"case_ref": item.review.case_ref, "severity": item.review.severity}
        for item in outbox.pending()
    ]
    return {"pending": len(items), "items": _redacted(items), "detail": "queued, not submitted"}


def verify_audit_trail(settings: Settings | None = None) -> dict[str, Any]:
    """Verify the audit trail's hash chain and its external head anchor.

    Returns:
      A dict with ``ok``, the record counts and a ``detail`` string. ``ok`` is false for an
      edited, deleted or reordered record, and, when an external anchor is configured, for a
      truncated tail as well.
    """
    resolved = settings or Settings.load()
    audit = _container(resolved).audit
    verify = getattr(audit, "verify", None)
    if verify is None:
        raise NotImplementedError(
            f"the {resolved.profile} audit adapter does not expose chain verification; a "
            "managed WORM sink is verified by its own retention policy, not from here"
        )
    report = verify()
    return {
        "ok": report.ok,
        "entries": report.entries,
        "chained": report.chained,
        "legacy": report.legacy,
        "first_bad_seq": report.first_bad_seq,
        "detail": report.detail,
        "anchored": bool(resolved.audit_anchor_path),
    }


#: The tool table. The agent card advertises exactly these, by function name.
TOOL_FUNCTIONS = (screen_name, screen_payment_message, list_disposition_queue, verify_audit_trail)


def build_function_tools() -> list[FunctionTool]:
    """Wrap each callable as a runtime FunctionTool (the only ADK-dependent code path)."""
    from google.adk.tools import FunctionTool

    return [FunctionTool(func=function) for function in TOOL_FUNCTIONS]
