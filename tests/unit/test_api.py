"""API surface: verified-principal identity, fail-closed S2S, security headers.

The client comes from the shared ``api_client`` fixture, which pins a loopback peer: the
app-object exposure guard refuses the unauthenticated local posture to any other peer, and
TestClient's default peer is the literal host "testclient".
"""

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

_TOKEN_ENV = "SANCTIONS_S2S_TOKEN"


def _screen_body(subject: str = "Volkov Metals OJSC (FICTIONAL)") -> dict[str, str]:
    return {"subject": subject, "kind": "entity"}


def test_screen_uses_the_verified_principal_as_actor(api_client: TestClient) -> None:
    resp = api_client.post(
        "/v1/screen",
        json=_screen_body(),
        headers={"X-Dev-Persona": "auditor"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["band"] == "confirmed"
    assert body["recommendation"] == "true_match"
    assert body["requires_human_review"] is True
    # Rule R8: the disposition was routed, not merely flagged (see test_review_routing.py).
    assert body["review_ref"]


def test_an_ownership_graph_of_another_tenant_is_not_resolvable(
    api_client: TestClient,
) -> None:
    """Object-level authorization: naming a UBO graph key is not entitlement to the graph.

    The verified principal `other-tenant` belongs to `other-bank`, and the fixture Doc1 graph is
    tagged `demo-bank`. `OwnershipGraphPort.resolve` took a client-supplied `subject_id` and no
    principal, so any authenticated caller who named a key had that subject's beneficial owners,
    who are NATURAL PERSONS, resolved and screened on their behalf. Doc1 publishes the owning
    tenant on the contract; this consumer was dropping it.

    The screen still succeeds and still bands the name: refusing the ownership enrichment is not
    refusing the request. What must not happen is another bank's ownership structure being read.
    """
    resp = api_client.post(
        "/v1/screen",
        json={
            "subject": "Acme Holdings Pte Ltd (FICTIONAL)",
            "kind": "entity",
            "subject_id": "acme",
        },
        headers={"X-Dev-Persona": "other-tenant"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["owners_screened"] == 0, (
        f"a foreign tenant resolved the ownership graph: {body['owners_screened']} owner(s)"
    )


def test_the_home_tenant_still_resolves_its_own_ownership_graph(
    api_client: TestClient,
) -> None:
    """The control. Without it, the assertion above is satisfied by ownership being switched off."""
    resp = api_client.post(
        "/v1/screen",
        json={
            "subject": "Acme Holdings Pte Ltd (FICTIONAL)",
            "kind": "entity",
            "subject_id": "acme",
        },
        headers={"X-Dev-Persona": "analyst"},
    )
    assert resp.status_code == 200
    assert resp.json()["owners_screened"] == 2


def test_unknown_persona_is_401(api_client: TestClient) -> None:
    resp = api_client.post(
        "/v1/screen",
        json=_screen_body("Beta Stationery Pte Ltd (FICTIONAL)"),
        headers={"X-Dev-Persona": "ghost"},
    )
    assert resp.status_code == 401


def test_healthz_reports_profile_and_region(api_client: TestClient) -> None:
    body = api_client.get("/healthz").json()
    assert body["status"] == "ok"
    assert body["profile"] == "local"
    assert body["region"] == "asia-southeast1"


def test_security_headers_present(api_client: TestClient) -> None:
    headers = api_client.get("/healthz").headers
    assert headers["Content-Security-Policy"] == "frame-ancestors 'self'"
    assert headers["X-Content-Type-Options"] == "nosniff"


@pytest.fixture()
def token_env(monkeypatch: pytest.MonkeyPatch) -> Iterator[str]:
    monkeypatch.setenv(_TOKEN_ENV, "s3cret-service-token")
    yield "s3cret-service-token"


def test_s2s_endpoint_open_when_secret_unset(
    api_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv(_TOKEN_ENV, raising=False)
    assert api_client.post("/v1/audit/ping").status_code == 200


def test_s2s_endpoint_rejects_missing_token_when_enforced(
    api_client: TestClient, token_env: str
) -> None:
    assert api_client.post("/v1/audit/ping").status_code == 401


def test_s2s_endpoint_accepts_correct_token(api_client: TestClient, token_env: str) -> None:
    resp = api_client.post("/v1/audit/ping", headers={"Authorization": f"Bearer {token_env}"})
    assert resp.status_code == 200
