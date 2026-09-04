"""Rule R8: a screening disposition is ROUTED to human-review-console, not left in a per-repo
boolean.

The system never clears a match on its own, so EVERY disposition routes, including a proposed
clear. The severity of the disposition sets the control level: a confirmed match demands dual
control. The assertions here are about the ROUTING, not a flag: a disposition produces an
outbound review, the payload leaves redacted, and the on-prem placeholder refuses rather than
swallowing the escalation.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from sanctions_screening.adapters.gcp.review_router import CloudReviewRouter
from sanctions_screening.adapters.local.review_router import LocalReviewRouter
from sanctions_screening.adapters.onprem.review_router import OnPremReviewRouter
from sanctions_screening.api.app import app
from sanctions_screening.config import Settings, build_container
from sanctions_screening.domain.kernel import Severity
from sanctions_screening.domain.models import PartyKind, ScreeningRequest, ScreeningResult
from sanctions_screening.service_factory import build_screening_service


def _settings(profile: str = "local") -> Settings:
    return Settings(profile=profile, audit_path=":memory:", tenant="demo-bank")


def _result(subject: str, kind: PartyKind = PartyKind.ENTITY) -> ScreeningResult:
    service = build_screening_service(build_container(_settings()))
    return service.screen(
        ScreeningRequest(subject=subject, kind=kind), actor="analyst@bank.example"
    )


def test_a_disposition_produces_an_outbound_review() -> None:
    router = LocalReviewRouter(_settings())
    ref = router.route(_result("Volkov Metals OJSC (FICTIONAL)"), maker="analyst@bank.example")
    assert ref, "routing must return a reference, so the caller can record where it went"
    pending = router.outbox.pending()
    assert len(pending) == 1
    review = pending[0].review
    assert review.maker == "analyst@bank.example"
    assert review.tenant == "demo-bank"
    assert review.severity == Severity.CRITICAL.value
    assert review.source_key, "a durable outbox needs an idempotency key"


def test_a_confirmed_match_demands_dual_control() -> None:
    router = LocalReviewRouter(_settings())
    router.route(_result("Volkov Metals OJSC (FICTIONAL)"), maker="analyst@bank.example")
    assert router.outbox.pending()[0].review.required_approvals == 2


def test_a_clean_disposition_still_routes_but_needs_a_single_approver() -> None:
    """The system never clears a match itself: a proposed clear is still a human decision."""
    router = LocalReviewRouter(_settings())
    router.route(_result("Beta Stationery Pte Ltd (FICTIONAL)"), maker="analyst@bank.example")
    review = router.outbox.pending()[0].review
    assert review.required_approvals == 1
    assert review.severity == Severity.LOW.value


def test_the_payload_is_redacted_before_it_leaves_the_process() -> None:
    """human-review-console is a shared sink; a raw identifier must never reach the wire."""
    service = build_screening_service(build_container(_settings()))
    result = service.screen(
        ScreeningRequest(
            subject="Dmitri Volkov (FICTIONAL)",
            kind=PartyKind.INDIVIDUAL,
            context="NRIC S1234567D on file",
        ),
        actor="analyst@bank.example",
    )
    router = LocalReviewRouter(_settings())
    router.route(result, maker="analyst@bank.example")
    review = router.outbox.pending()[0].review
    wire = repr(review.to_payload())
    assert "S1234567D" not in wire
    assert "REDACTED" in wire


def test_the_managed_router_refuses_when_no_console_is_configured() -> None:
    router = CloudReviewRouter(Settings(profile="gcp", audit_path=":memory:", review_url=""))
    with pytest.raises(RuntimeError, match="R8"):
        router.route(_result("Volkov Metals OJSC (FICTIONAL)"), maker="analyst@bank.example")


def test_the_onprem_placeholder_refuses_rather_than_dropping_the_escalation() -> None:
    router = OnPremReviewRouter(_settings("onprem"))
    with pytest.raises(NotImplementedError, match="R8"):
        router.route(_result("Volkov Metals OJSC (FICTIONAL)"), maker="analyst@bank.example")


def test_the_api_routes_every_disposition_in_the_same_request() -> None:
    """The serving path, not just the adapter: a disposition must not depend on a later job."""
    client = TestClient(app, client=("127.0.0.1", 50000))
    confirmed = client.post(
        "/v1/screen",
        json={"subject": "Volkov Metals OJSC (FICTIONAL)", "kind": "entity"},
        headers={"X-Dev-Persona": "auditor"},
    ).json()
    assert confirmed["requires_human_review"] is True
    assert confirmed["review_ref"], "a disposition with no routing reference went nowhere"

    clean = client.post(
        "/v1/screen",
        json={"subject": "Beta Stationery Pte Ltd (FICTIONAL)", "kind": "entity"},
        headers={"X-Dev-Persona": "auditor"},
    ).json()
    # Even a clean screen routes: the system never clears a match on its own.
    assert clean["requires_human_review"] is True
    assert clean["review_ref"]
