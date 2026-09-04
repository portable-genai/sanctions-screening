#!/usr/bin/env python3
"""Evaluation gate for Sanctions Screening Copilot (G2).

Two named layers via ``--mode``:

* **smoke** (default) is the offline pre-merge check: it drives the real ``ScreeningService``
  against a golden set with SDK-free local adapters and scores its metrics against the DATASET'S OWN
  ``expected`` oracle, never against the pipeline's own verdict. Three metrics are also proven ABLE
  TO GO RED via ``agent_eval_kit.assert_each_can_go_red``: a metric that cannot fail on a crafted
  bad case is not a metric. * **gate** is the promotion verdict from the shared model-quality-gate
  authority (requires the ``gcp`` profile).

Exit is ``0`` iff every metric meets its threshold (and, in gate mode, the authority agrees).
"""

from __future__ import annotations

import json
import os
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any

from agent_eval_kit import (
    EvalMetricResult,
    EvalReport,
    PromotionGateClient,
    assert_each_can_go_red,
    eval_main,
)
from pii_kit import pack_leak

from sanctions_screening.adapters.local.audit import LocalAuditAdapter
from sanctions_screening.adapters.local.ownership_graph import FIXTURE_TENANT
from sanctions_screening.config import Settings, build_container
from sanctions_screening.domain.listpacks import validate_all_packs
from sanctions_screening.domain.memo import is_grounded
from sanctions_screening.domain.models import (
    PartyKind,
    Recommendation,
    ScreeningRequest,
    ScreeningResult,
)
from sanctions_screening.domain.pii import PII_PATTERNS
from sanctions_screening.service_factory import build_screening_service

_REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DATASET = _REPO_ROOT / "eval" / "datasets" / "golden_cases.jsonl"

THRESHOLDS: dict[str, float] = {
    "recommendation_accuracy": 0.80,
    "no_false_clear": 1.0,
    "screening_coverage": 1.0,
    "pack_schema_validity": 1.0,
    "memo_groundedness": 1.0,
    "pii_safety": 0.99,
}
#: The registered model-quality-gate metric bundle for this vertical (model-quality-gate owns the
#: metrics + thresholds).
_BUNDLE = "sanctions-screening"


def _load(path: Path) -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        cases.append(json.loads(line))
    if not cases:
        raise SystemExit(f"{path}: golden dataset is empty")
    return cases


def _mean(scores: list[float]) -> float:
    return round(sum(scores) / len(scores), 4) if scores else 0.0


def _screen(case: Mapping[str, Any]) -> ScreeningResult:
    """Screen one case on a fresh SDK-free local service (deterministic, so replayable)."""
    service = build_screening_service(build_container(Settings(profile="local", tenant="demo")))
    kind = str(case.get("kind", "entity"))
    request = ScreeningRequest(
        subject=str(case["subject"]),
        kind=PartyKind(kind) if kind in tuple(PartyKind) else PartyKind.UNKNOWN,
        subject_id=str(case.get("subject_id", "")),
        context=str(case.get("context", "")),
    )
    return service.screen(request, actor="eval-bot", tenant=FIXTURE_TENANT)


# --------------------------------------------------------------------------- #
# The scorers. Each reads the DATASET'S expected oracle, never the pipeline's verdict.
# --------------------------------------------------------------------------- #
def score_recommendation(case: Mapping[str, Any]) -> float:
    """1.0 when the engine's recommendation equals the oracle's, else 0.0."""
    expected = str(case["expected"]["recommendation"])
    return 1.0 if _screen(case).recommendation.value == expected else 0.0


def score_no_false_clear(case: Mapping[str, Any]) -> float:
    """A case the oracle labels a true match must NOT be recommended as a false positive."""
    if not case["expected"].get("is_true_match"):
        return 1.0
    return 0.0 if _screen(case).recommendation is Recommendation.FALSE_POSITIVE else 1.0


def score_coverage(case: Mapping[str, Any]) -> float:
    """The count of owners screened must equal the oracle's expected owner count."""
    expected = int(case["expected"].get("owners", 0))
    return 1.0 if _screen(case).owners_screened == expected else 0.0


def score_memo_grounded(case: Mapping[str, Any]) -> float:
    """The disposition memo must contain no number the engine did not compute."""
    return 1.0 if _screen(case).memo.grounded else 0.0


# --------------------------------------------------------------------------- #
# Provable-red: a crafted bad case each metric MUST fail on, or it proves nothing.
# --------------------------------------------------------------------------- #
#: A clean name the oracle wrongly insists is a true match. The engine clears it, so
#: ``score_no_false_clear`` returns 0: exactly the failure the metric exists to catch. The green
#: case is a real designated party the engine confirms.
_RED_FALSE_CLEAR = {
    "subject": "Harmless Stationery Pte Ltd (FICTIONAL)",
    "kind": "entity",
    "expected": {"is_true_match": True},
}
_GREEN_TRUE_MATCH = {
    "subject": "Volkov Metals OJSC (FICTIONAL)",
    "kind": "entity",
    "expected": {"is_true_match": True, "recommendation": "true_match"},
}
#: The oracle here says false_positive while the engine confirms, so ``score_recommendation`` = 0.
_RED_RECOMMENDATION = {
    "subject": "Volkov Metals OJSC (FICTIONAL)",
    "kind": "entity",
    "expected": {"recommendation": "false_positive", "is_true_match": True},
}

#: A memo facts payload and two drafts: a grounded one, and one with a fabricated percentage.
_GROUNDING_FACTS: dict[str, Any] = {
    "subject": "Volkov Metals OJSC (FICTIONAL)",
    "matches": [{"name": "Volkov Metals OJSC (FICTIONAL)", "confidence": 100.0}],
    "owners_screened": 0,
}
_GREEN_MEMO = "Screening matched at confidence 100.0."
_RED_MEMO = "Screening matched at confidence 100.0 with a 42.5 percent stake."


def _assert_metrics_can_go_red() -> None:
    """Fail the eval if a headline metric cannot detect its own defect class."""
    assert_each_can_go_red(
        score_recommendation,
        {"recommendation": (_GREEN_TRUE_MATCH, _RED_RECOMMENDATION)},
        threshold=THRESHOLDS["recommendation_accuracy"],
        metric="recommendation_accuracy",
    )
    assert_each_can_go_red(
        score_no_false_clear,
        {"false_clear": (_GREEN_TRUE_MATCH, _RED_FALSE_CLEAR)},
        threshold=THRESHOLDS["no_false_clear"],
        metric="no_false_clear",
    )
    assert_each_can_go_red(
        lambda text: 1.0 if is_grounded(text, _GROUNDING_FACTS) else 0.0,
        {"groundedness": (_GREEN_MEMO, _RED_MEMO)},
        threshold=THRESHOLDS["memo_groundedness"],
        metric="memo_groundedness",
    )


def audit_surfaces(rows: Iterable[Mapping[str, Any]]) -> list[str]:
    """Every CONTENT-bearing field of each persisted audit row, citations included.

    ``redacted_summary`` is one field of several the WORM record keeps, and scoring it alone is
    how a metric ends up certifying the leak it exists to catch: the summary is masked, the
    citations stored beside it in the same row are not, and the identifier survives in a record
    the metric has just called clean. A citation's ``source_id`` is content here, not a bare
    locator, because a locator is built out of the identifiers the case supplied.

    ``actor`` is deliberately absent. It is the VERIFIED principal and an address by design, so a
    blanket scan over a whole row could never go green, and a metric that can never go green is a
    metric somebody switches off. Scanning the content fields is what makes this both sound and
    reachable.
    """
    out: list[str] = []
    for row in rows:
        out.append(str(row.get("redacted_summary", "")))
        out.append(json.dumps(row.get("citations", []), sort_keys=True, default=str))
    return out


def pii_safety(surfaces: Sequence[str], planted: Sequence[str]) -> float:
    """1.0 unless a raw identifier survived into an audit record, by pack row OR by literal.

    The pack scan uses the same rows the redactor masks with, so it catches PII the pipeline
    re-introduced after redaction; the planted-literal scan is an independent oracle that still
    fires when a pack row is narrowed or broken (the two-part scorer lesson from the C4 rollout).
    """
    pack_leaked = any(pack_leak(text, PII_PATTERNS) for text in surfaces)
    literal_leaked = any(token in text for token in planted for text in surfaces)
    return 0.0 if (pack_leaked or literal_leaked) else 1.0


def run_smoke(dataset: Path) -> EvalReport:
    cases = _load(dataset)
    _assert_metrics_can_go_red()

    recommendation = _mean([score_recommendation(c) for c in cases])
    no_false_clear = _mean([score_no_false_clear(c) for c in cases])
    coverage = _mean([score_coverage(c) for c in cases])
    grounded = _mean([score_memo_grounded(c) for c in cases])
    pack_validity = 1.0 if not validate_all_packs() else 0.0

    # pii_safety: no raw identifier may survive into any audit record. One shared service so the
    # audit trail holds every case; the planted-literal check is an independent oracle that fires
    # even if a redaction row is broken.
    service = build_screening_service(build_container(Settings(profile="local", tenant="demo")))
    audit = service._audit  # noqa: SLF001 - the eval inspects the trail it just wrote
    assert isinstance(audit, LocalAuditAdapter)
    for case in cases:
        kind = str(case.get("kind", "entity"))
        service.screen(
            ScreeningRequest(
                subject=str(case["subject"]),
                kind=PartyKind(kind) if kind in tuple(PartyKind) else PartyKind.UNKNOWN,
                subject_id=str(case.get("subject_id", "")),
                context=str(case.get("context", "")),
            ),
            actor="eval-bot",
            tenant=FIXTURE_TENANT,
        )
    surfaces = audit_surfaces(audit.log.read_all())
    planted = [str(c["planted"]) for c in cases if c.get("planted")]

    results = (
        EvalMetricResult.scored(
            "recommendation_accuracy", recommendation, THRESHOLDS["recommendation_accuracy"]
        ),
        EvalMetricResult.scored("no_false_clear", no_false_clear, THRESHOLDS["no_false_clear"]),
        EvalMetricResult.scored("screening_coverage", coverage, THRESHOLDS["screening_coverage"]),
        EvalMetricResult.scored(
            "pack_schema_validity", pack_validity, THRESHOLDS["pack_schema_validity"]
        ),
        EvalMetricResult.scored("memo_groundedness", grounded, THRESHOLDS["memo_groundedness"]),
        EvalMetricResult.scored(
            "pii_safety", pii_safety(surfaces, planted), THRESHOLDS["pii_safety"]
        ),
    )
    return EvalReport(dataset=str(dataset), results=results, n_examples=len(cases))


def run_gate(dataset: Path) -> tuple[EvalReport, bool]:
    settings = Settings.load()
    if settings.profile != "gcp":
        raise SystemExit(
            "--mode gate is the promotion authority and requires "
            f"SANCTIONS_PROFILE=gcp (got {settings.profile!r}); "
            "run --mode smoke for the offline pre-merge check."
        )
    client = PromotionGateClient(
        os.environ.get("SANCTIONS_QUALITY_URL", "http://localhost:8084"),
        bundle=_BUNDLE,
        model="gemini-3.5-flash",
    )
    return client.evaluate(str(dataset)), client.gate(str(dataset))


if __name__ == "__main__":
    raise SystemExit(
        eval_main(
            smoke=run_smoke,
            gate=run_gate,
            default_dataset=DEFAULT_DATASET,
            description="Offline / model-quality-gate for G2.",
        )
    )
