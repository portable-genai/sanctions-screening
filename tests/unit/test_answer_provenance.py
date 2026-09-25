"""The service half of the model pills: which model ANSWERED, and whether it searched.

The console shows two pills at the top right: the model that answered the last request, and
``Search`` when that answer used an online search tool. Both come from response headers the kit
emits (``install_answer_provenance`` in ``api/app.py``) for whatever the model adapters NOTED as
they called. Before a request is answered the pill shows ``generator_model`` from ``/healthz``,
so that value must be the model the bound adapter calls, never one a configuration flag names
while the adapter calls another.

Under ``local`` the narration port is bound to the deterministic memo builder, which notes
itself as the same stub name ``generator_model`` reports, so a screening answers with that name
and the configured and answered pills agree. The managed narration and adverse-media adapters
are deployment-wired placeholders that raise, so they have no successful call to note yet.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from hex_service_kit import provenance

from sanctions_screening import config
from sanctions_screening.adapters.local.adverse_media import LocalAdverseMediaAdapter
from sanctions_screening.adapters.local.narration import LocalNarrationAdapter
from sanctions_screening.config import OFFLINE_STUB_MODEL, Settings

from tests import REPO_ROOT

ANSWERED_BY = "x-answered-by"
SEARCH_USED = "x-search-used"


def _screen(api_client: TestClient) -> dict[str, str]:
    response = api_client.post(
        "/v1/screen",
        json={"subject": "Volkov Metals OJSC (FICTIONAL)", "kind": "entity"},
        headers={"X-Dev-Persona": "analyst"},
    )
    assert response.status_code == 200, response.text
    return dict(response.headers)


def test_a_screening_names_the_stub_that_drafted_its_memo(api_client: TestClient) -> None:
    """The memo is the model-shaped step; offline its drafter answers, and says so by name."""
    headers = _screen(api_client)
    assert headers[ANSWERED_BY] == OFFLINE_STUB_MODEL
    assert SEARCH_USED not in headers, "the offline adverse-media fixture never goes online"


def test_the_answered_name_is_the_configured_name_under_local() -> None:
    """The dimmed pill and the solid pill name one thing for one binding, never two."""
    assert Settings.load().generator_model == OFFLINE_STUB_MODEL


def test_the_local_drafter_notes_itself_only_inside_a_request() -> None:
    adapter = LocalNarrationAdapter(Settings.load())
    facts = {"subject": "Example (FICTIONAL)", "band": "clear", "recommendation": "no_match"}
    with provenance.scope() as record:
        adapter.draft_memo(facts)
    assert record.models == [OFFLINE_STUB_MODEL]
    assert record.search_used is False
    # Outside a request (the CLI, an eval run) noting is a no-op, never an error.
    adapter.draft_memo(facts)


def test_a_search_using_call_is_reported_and_does_not_leak_into_the_next_request(
    api_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A grounded adverse-media search sets Search; the next request starts from nothing."""
    original = LocalAdverseMediaAdapter.search

    def searching(self: LocalAdverseMediaAdapter, *args: object, **kwargs: object) -> object:
        provenance.note_search()  # what a search tool attached to the call would note
        return original(self, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(LocalAdverseMediaAdapter, "search", searching)
    headers = _screen(api_client)
    assert headers[ANSWERED_BY] == OFFLINE_STUB_MODEL
    assert headers[SEARCH_USED] == "true"
    monkeypatch.setattr(LocalAdverseMediaAdapter, "search", original)
    assert SEARCH_USED not in _screen(api_client)


def test_health_names_no_model_it_did_not_answer_with(api_client: TestClient) -> None:
    """/healthz answers nothing, so it carries neither header."""
    response = api_client.get("/healthz")
    assert response.status_code == 200
    assert ANSWERED_BY not in response.headers
    assert SEARCH_USED not in response.headers


def test_generator_model_is_the_setting_the_adapter_reads_and_no_flag_swaps_it() -> None:
    """The latent false banner: a flag that moved the pill but not the model that answered.

    A resolver once named ``models.hard_reasoning`` when ``models.use_hard_reasoning`` was set,
    while a managed adapter called ``models.reasoning`` and never read the flag. The pill then
    named a model that never answered. The flag is gone; a stray one in a settings object must
    change nothing.
    """
    models = SimpleNamespace(
        reasoning="the-model-the-adapter-calls",
        hard_reasoning="a-model-nobody-calls",
        use_hard_reasoning=True,
    )
    named = config._model_from_settings(SimpleNamespace(models=models), "models.reasoning")
    assert named == "the-model-the-adapter-calls"


def test_the_hard_reasoning_flag_does_not_exist() -> None:
    settings_file = (REPO_ROOT / "config" / "settings.yaml").read_text(encoding="utf-8")
    assert "use_hard_reasoning" not in settings_file
    for source in sorted((REPO_ROOT / "src").rglob("*.py")):
        assert "use_hard_reasoning" not in source.read_text(encoding="utf-8"), source
