"""Review routing has a switch, default on, and every caller says what happened to a hand-off.

The fleet's runtime-control contract (2026-09-24). Review routing is the one cheap runtime
control this service has: ``SANCTIONS_REVIEW_ROUTING`` is read in three states; off binds a
disabled router and says so at startup; on under the managed profile refuses to boot without a
console; and the API, the agent tools and the CLI report ``review_routing`` rather than failing
an already-scored, already-audited screening when the console is unreachable.
"""

from __future__ import annotations

import dataclasses
import logging
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from sanctions_screening.adapters.controls import (
    DisabledReviewRouter,
    RecordingReviewRouter,
    ReviewRouting,
)
from sanctions_screening.agent import tools
from sanctions_screening.api import app as api_module
from sanctions_screening.api.app import app
from sanctions_screening.cli.main import main as cli_main
from sanctions_screening.config import (
    REVIEW_ROUTING_ENV,
    Container,
    ControlSwitches,
    ProfileChoice,
    Settings,
    build_container,
    warn_switched_off,
)
from sanctions_screening.domain.models import PartyKind, ScreeningRequest, ScreeningResult
from sanctions_screening.envread import ConfiguredEmptyError
from sanctions_screening.service_factory import build_screening_service

_LOOPBACK = ("127.0.0.1", 50000)
_SUBJECT = "Volkov Metals OJSC (FICTIONAL)"
_LOCAL_ROUTE = "sanctions_screening.adapters.local.review_router.LocalReviewRouter.route"


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.delenv(REVIEW_ROUTING_ENV, raising=False)
    monkeypatch.delenv("HUMAN_REVIEW_URL", raising=False)
    # The API caches its container for the process; each test here states its own posture.
    api_module._container.cache_clear()
    yield
    api_module._container.cache_clear()


def _settings(**overrides: object) -> Settings:
    return Settings(profile="local", audit_path=":memory:", tenant="demo-bank", **overrides)  # type: ignore[arg-type]


def _result() -> ScreeningResult:
    service = build_screening_service(build_container(_settings()))
    return service.screen(
        ScreeningRequest(subject=_SUBJECT, kind=PartyKind.ENTITY), actor="analyst@bank.example"
    )


def _gcp(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "sanctions_screening.config.resolve_profile",
        lambda environ=None: ProfileChoice("gcp", True),
    )


# --------------------------------------------------------------------------- #
# Three states
# --------------------------------------------------------------------------- #
def test_routing_is_on_when_nothing_is_said() -> None:
    assert Settings.load().controls == ControlSwitches(review_routing=True)


def test_routing_switched_off_is_off(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(REVIEW_ROUTING_ENV, "off")
    assert Settings.load().controls.switched_off() == (REVIEW_ROUTING_ENV,)


def test_an_emptied_switch_refuses_at_load(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(REVIEW_ROUTING_ENV, "")
    with pytest.raises(ConfiguredEmptyError, match=REVIEW_ROUTING_ENV):
        Settings.load()


def test_an_unrecognised_switch_refuses_at_load(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(REVIEW_ROUTING_ENV, "sometimes")
    with pytest.raises(ValueError, match=REVIEW_ROUTING_ENV):
        Settings.load()


# --------------------------------------------------------------------------- #
# Off binds the disabled router, and says so once
# --------------------------------------------------------------------------- #
def test_off_binds_the_disabled_router() -> None:
    settings = _settings(controls=ControlSwitches(review_routing=False))
    assert isinstance(Container(settings).review_router, DisabledReviewRouter)


def test_on_binds_the_profile_router() -> None:
    assert not isinstance(Container(_settings()).review_router, DisabledReviewRouter)


def test_the_off_posture_is_logged_once_however_many_containers(
    caplog: pytest.LogCaptureFixture,
) -> None:
    warn_switched_off.cache_clear()
    settings = _settings(controls=ControlSwitches(review_routing=False))
    with caplog.at_level(logging.WARNING, logger="sanctions_screening.config"):
        for _ in range(3):
            build_container(settings)
    assert caplog.text.count(REVIEW_ROUTING_ENV) == 1


# --------------------------------------------------------------------------- #
# On has to work: checked at boot under the managed profile
# --------------------------------------------------------------------------- #
def test_routing_on_under_gcp_without_a_console_refuses_at_boot(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _gcp(monkeypatch)
    with pytest.raises(ConfiguredEmptyError, match="HUMAN_REVIEW_URL"):
        Settings.load()


def test_routing_stated_off_under_gcp_needs_no_console(monkeypatch: pytest.MonkeyPatch) -> None:
    _gcp(monkeypatch)
    monkeypatch.setenv(REVIEW_ROUTING_ENV, "false")
    assert Settings.load().controls.review_routing is False


def test_routing_on_under_gcp_with_a_console_loads(monkeypatch: pytest.MonkeyPatch) -> None:
    _gcp(monkeypatch)
    monkeypatch.setenv("HUMAN_REVIEW_URL", "https://review.example.test")
    assert Settings.load().review_url == "https://review.example.test"


# --------------------------------------------------------------------------- #
# The four routing outcomes
# --------------------------------------------------------------------------- #
class _Accepting:
    def route(self, result: ScreeningResult, *, maker: str, tenant: str = "") -> str:
        return "review-1"


class _Refusing:
    def route(self, result: ScreeningResult, *, maker: str, tenant: str = "") -> str:
        raise ConnectionError("console unreachable")


def test_routing_outcomes_take_each_of_their_four_values() -> None:
    result = _result()
    assert result.requires_human_review

    # Every real disposition routes; a result that did not require review is built by hand.
    not_required = RecordingReviewRouter(_Accepting())
    unflagged = dataclasses.replace(result, requires_human_review=False)
    assert not_required.route(unflagged, maker="m") == ""
    assert not_required.outcome is ReviewRouting.NOT_REQUIRED

    routed = RecordingReviewRouter(_Accepting())
    assert routed.route(result, maker="m") == "review-1"
    assert routed.outcome is ReviewRouting.ROUTED

    off = RecordingReviewRouter(DisabledReviewRouter(_settings()))
    assert off.route(result, maker="m") == ""
    assert off.outcome is ReviewRouting.OFF


def test_a_failed_hand_off_is_reported_and_logged_never_raised(
    caplog: pytest.LogCaptureFixture,
) -> None:
    failed = RecordingReviewRouter(_Refusing())
    with caplog.at_level(logging.WARNING, logger="sanctions_screening.adapters.controls"):
        assert failed.route(_result(), maker="m") == ""
    assert failed.outcome is ReviewRouting.FAILED
    assert "ConnectionError" in caplog.text


# --------------------------------------------------------------------------- #
# Every caller reports it: the API, the agent tools, the CLI
# --------------------------------------------------------------------------- #
def _screen() -> dict[str, object]:
    response = TestClient(app, client=_LOOPBACK).post(
        "/v1/screen",
        json={"subject": _SUBJECT, "kind": "entity"},
        headers={"X-Dev-Persona": "auditor"},
    )
    assert response.status_code == 200
    return response.json()


def test_the_api_reports_a_routed_hand_off() -> None:
    body = _screen()
    assert body["review_routing"] == "routed"
    assert body["review_ref"]


def test_the_api_reports_routing_off(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(REVIEW_ROUTING_ENV, "off")
    body = _screen()
    assert body["review_routing"] == "off"
    assert body["review_ref"] == ""


def test_the_api_reports_a_failed_hand_off_instead_of_failing_the_screening(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(_LOCAL_ROUTE, _Refusing.route)
    body = _screen()
    assert body["review_routing"] == "failed"
    assert body["review_ref"] == ""


def test_the_name_tool_reports_the_hand_off() -> None:
    payload = tools.screen_name(_SUBJECT, tenant="demo-bank", settings=_settings())
    assert payload["review_routing"] == "routed"


def test_the_payment_tool_reports_routing_off() -> None:
    settings = _settings(controls=ControlSwitches(review_routing=False))
    payload = tools.screen_payment_message(
        _SUBJECT, {"Dbtr": _SUBJECT}, tenant="demo-bank", settings=settings
    )
    assert payload["review_routing"] == "off"
    assert payload["review_ref"] == ""


def test_the_cli_reports_the_hand_off(capsys: pytest.CaptureFixture[str]) -> None:
    assert cli_main(["screen", _SUBJECT]) == 0
    assert "human review hand-off : routed" in capsys.readouterr().out
