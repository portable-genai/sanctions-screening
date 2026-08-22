"""The screening path opens ONE span, and that span carries no content.

A trace backend is not the WORM audit trail. It has no redaction stage, no retention policy
written against a regulator's requirement, and a far wider read audience than the audit store.
So the value of tracing the screening path depends entirely on the span carrying structural
attributes only: which action, whose, which kind of party, how long. A subject name, a pasted
identifier, the analyst's free-text context or the drafted disposition memo reaching a span has
left the boundary that the redact-before-anything calls exist to hold, and it has left it
silently.

The content case drives the request whose context carries a planted NRIC, so the check runs
against input that would actually leak if any attribute were content-shaped.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

import pytest

from sanctions_screening.config import build_container
from sanctions_screening.domain.listpacks import load_guidance, load_list_entries
from sanctions_screening.domain.match_engine import MatchEngine
from sanctions_screening.domain.models import ScreeningRequest, ScreeningResult
from sanctions_screening.domain.policy import load_match_policy
from sanctions_screening.domain.screening_service import ScreeningService

from tests.conftest import local_settings
from tests.fixtures import sample_cases

#: Every attribute key the screening span is allowed to carry. A confirmed match that started
#: explaining itself on the span (the band, the subject, a context fragment) would widen this
#: set, which is the point of asserting on the set rather than on the individual keys.
_SCREEN_KEYS = {"action", "actor", "kind"}


class _RecordingTracer:
    """Captures every span name and attribute so the test can inspect what was emitted."""

    def __init__(self) -> None:
        self.spans: list[tuple[str, dict[str, str]]] = []

    @contextmanager
    def span(self, name: str, **attributes: str) -> Iterator[None]:
        self.spans.append((name, dict(attributes)))
        yield

    def record_token_usage(self, usage: object, model: str) -> None:
        return None


def _screen(request: ScreeningRequest) -> tuple[_RecordingTracer, ScreeningResult]:
    """The REAL local adapters for every port except the tracer under inspection."""
    container = build_container(local_settings())
    tracer = _RecordingTracer()
    policy = load_match_policy(container.settings.policy)
    service = ScreeningService(
        container.audit,
        container.ownership_graph,
        container.adverse_media,
        container.narration,
        tracer=tracer,  # type: ignore[arg-type]
        engine=MatchEngine(policy),
        list_entries=load_list_entries(),
        guidance=load_guidance(),
        policy=policy,
    )
    result = service.screen(request, actor=sample_cases.ACTOR)
    return tracer, result


def _emitted(tracer: _RecordingTracer) -> str:
    """Every span name, attribute KEY and attribute VALUE, as one searchable blob."""
    parts: list[str] = []
    for name, attributes in tracer.spans:
        parts.append(name)
        parts.extend(attributes)
        parts.extend(attributes.values())
    return " ".join(parts)


def test_screening_one_subject_opens_exactly_one_named_span() -> None:
    tracer, _ = _screen(sample_cases.CLEAN_CASE)
    assert [name for name, _ in tracer.spans] == ["sanctions.screen"]


def test_the_span_carries_the_structural_attributes_an_operator_needs() -> None:
    """Enough to answer "whose screening is slow, and on which party kind", and nothing more."""
    tracer, _ = _screen(sample_cases.CLEAN_CASE)
    _, attributes = tracer.spans[0]
    assert attributes["action"] == "screen"
    assert attributes["actor"] == sample_cases.ACTOR
    assert attributes["kind"] == sample_cases.CLEAN_CASE.kind.value


@pytest.mark.parametrize(
    "request_case",
    [sample_cases.CLEAN_CASE, sample_cases.CONFIRMED_CASE, sample_cases.PII_CASE],
    ids=["clear", "confirmed", "pii"],
)
def test_the_attribute_set_is_a_fixed_allowlist_whatever_the_band(
    request_case: ScreeningRequest,
) -> None:
    """A confirmed match must not start attaching its hits to the span to explain itself."""
    tracer, _ = _screen(request_case)
    for _, attributes in tracer.spans:
        assert set(attributes) == _SCREEN_KEYS


def test_no_span_attribute_carries_request_content_or_the_planted_identifier() -> None:
    """The request used here has an NRIC planted in its context, so a leak would show."""
    tracer, result = _screen(sample_cases.PII_CASE)
    emitted = _emitted(tracer)

    forbidden: list[str] = [
        sample_cases.PLANTED_NRIC,
        sample_cases.PII_CASE.subject,
        sample_cases.PII_CASE.context,
        sample_cases.PII_CASE.dob,
        "ops@volkov.example",
        # The drafted memo and the audit summary are the other content-shaped values in
        # reach of this call.
        result.memo.text,
        result.summary,
    ]
    for literal in forbidden:
        assert literal, "an empty needle would pass this test for the wrong reason"
        assert literal not in emitted, f"a span attribute carried {literal!r}"
        assert literal.lower() not in emitted.lower(), f"a span attribute carried {literal!r}"

    # Belt and braces: no distinctive token of the free-text context or the subject name appears
    # either, so a truncated or reformatted fragment cannot slip through the whole-string checks.
    source = f"{sample_cases.PII_CASE.context} {sample_cases.PII_CASE.subject}"
    tokens = {token.strip("().,:;") for token in source.split() if len(token.strip("().,:;")) > 5}
    emitted_tokens = set(emitted.lower().split())
    assert tokens, "the fixture must carry distinctive text for this check to mean anything"
    assert not {token.lower() for token in tokens} & emitted_tokens


def test_every_emitted_attribute_value_is_a_string_the_port_declares() -> None:
    """``span(name, **attributes: str)``: a non-string would serialise however the SDK felt."""
    tracer, _ = _screen(sample_cases.CONFIRMED_CASE)
    values: list[Any] = [value for _, attributes in tracer.spans for value in attributes.values()]
    assert values
    assert all(isinstance(value, str) for value in values)
