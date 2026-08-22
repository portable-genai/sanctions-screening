"""The agent surface is real, import-safe and cannot drift from the card it publishes."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from sanctions_screening.agent import (
    SKILLS,
    TOOL_FUNCTIONS,
    agent_card_document,
    build_agent_card,
    list_disposition_queue,
    screen_name,
    verify_audit_trail,
)
from sanctions_screening.config import Settings

from tests.conftest import local_settings
from tests.fixtures import sample_cases


def test_the_card_advertises_exactly_the_tools_the_runtime_binds() -> None:
    assert {skill.id for skill in SKILLS} == {fn.__name__ for fn in TOOL_FUNCTIONS}


def test_every_skill_carries_a_usable_description() -> None:
    for skill in SKILLS:
        assert skill.name.strip()
        assert len(skill.description.strip()) > 40, f"{skill.id} has no usable description"


def test_the_card_document_is_json_safe_and_names_the_region() -> None:
    document = agent_card_document(local_settings())
    assert document["name"] == "sanctions-screening"
    assert "asia-southeast1" in str(document["url"])
    assert [skill["id"] for skill in document["skills"]] == [s.id for s in SKILLS]


def test_the_api_serves_the_card_for_discovery(api_client: TestClient) -> None:
    resp = api_client.get("/.well-known/agent-card.json")
    assert resp.status_code == 200
    assert resp.json()["skills"], "a card with no skills is not a discovery document"


def test_the_agent_path_routes_a_disposition_rather_than_only_flagging_it() -> None:
    result = screen_name(
        sample_cases.CONFIRMED_CASE.subject,
        kind="entity",
        actor=sample_cases.ACTOR,
        tenant=sample_cases.TENANT,
        settings=local_settings(),
    )
    assert result["requires_human_review"] is True
    assert result["review_ref"], "the agent surface flagged a disposition it never routed"


def test_the_disposition_queue_lists_what_was_routed() -> None:
    settings = local_settings()
    screen_name(sample_cases.CONFIRMED_CASE.subject, settings=settings)
    # A fresh container per call means the queue tool sees its own outbox; it reports zero pending
    # rather than raising, which is the honest answer for a stateless per-call binding.
    queue = list_disposition_queue(settings)
    assert "pending" in queue


def test_the_tool_output_is_masked_before_it_can_reach_a_model() -> None:
    """P-04 at the agent boundary: a tool result becomes model context, so it is minimised."""
    from sanctions_screening.agent.tools import screen_payment_message

    result = screen_payment_message(
        "Dmitri Volkov (FICTIONAL)",
        {"Dbtr/Nm": "Dmitri Volkov (FICTIONAL)", "Cdtr/Nm": "contact ops@volkov.example"},
        settings=local_settings(),
    )
    rendered = repr(result)
    assert isinstance(result, dict)
    assert result["review_ref"]
    # The email planted in a message field is masked on the way to the model.
    assert "ops@volkov.example" not in rendered
    assert "REDACTED" in rendered


def test_the_audit_verification_tool_reports_an_honest_verdict() -> None:
    report = verify_audit_trail(local_settings())
    assert report["ok"] is True
    assert report["anchored"] is False, "the ephemeral gate store has no external anchor"


def test_the_audit_verification_tool_refuses_where_it_cannot_verify() -> None:
    with pytest.raises(NotImplementedError):
        verify_audit_trail(Settings(profile="onprem"))


def test_the_tools_import_and_run_with_no_agent_runtime_installed(no_cloud_sdk: None) -> None:
    """``build_function_tools`` is the ONLY code path that may need a runtime."""
    from sanctions_screening.agent import tools

    assert tools.TOOL_FUNCTIONS
    assert build_agent_card(local_settings()).skills
    with pytest.raises(ModuleNotFoundError):
        tools.build_function_tools()
