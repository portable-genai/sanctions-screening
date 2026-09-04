# Model card: Sanctions Screening Copilot (G2)

This is a STARTER model card. It records the model boundary as built and the controls that must
be completed before a managed deployment. The deterministic engine is the system of record; the
model is a bounded, replaceable component that today is not even running.

**State on the shipped build: no model call executes on any profile.** The offline narration
adapter returns a deterministic memo, the managed adapter is a construction-only seam that
raises, and `managed_readiness.py` names it so the API preflight REFUSES to start a managed
process while it is on the primary journey. Everything below describes the boundary that is
already enforced around the model, so that wiring one in is a bounded change rather than a
re-architecture.

## What the model does, and does not do

- **Does**: narrate the disposition memo, and nothing else. `NarrationPort`
  (`ports/narration.py`) is the single seam a model sits behind in this service. Given the engine
  facts (the subject, the band, the proposed recommendation, the per-party matches with their
  list id, entry id and confidence, the owner matches, the owner count, the adverse-media
  headlines and the applicable guidance note) it restates them in prose for a reviewer. The
  return is treated as UNTRUSTED text: the caller validates it and discards it on any figure the
  engine did not compute.
- **Does NOT**: produce any number, band, verdict or recommendation. The match confidence, its
  four sub-scores and the arithmetic that produced them, the band, the false-clear guard, the
  cross-kind cap and the proposed disposition all come from `domain/match_engine.py` in pure
  stdlib; the band thresholds and blend weights come from `domain/policy.py` as the adopter's
  configuration; the worst-band rollup, the severity mapping and the always-true review flag come
  from `domain/screening_service.py`; party extraction from a payment message is a data table in
  `domain/message_fields.py`; the list and guidance data come from `domain/listpacks.py`; and the
  memo that is actually shown when a draft is discarded comes from `domain/memo.py::build_memo`.
  `tests/unit/test_memo.py::test_the_numbers_are_identical_with_the_generation_adapter_stubbed_out`
  screens the same subject three ways (the real deterministic narrator, a narrator stubbed to
  silence, and one that hallucinates a percentage) and asserts every consequential number and
  verdict is byte-identical across all three, so a model change cannot move a figure.

There is no speech, audio, vision or OCR port in this repo, and no retrieval port: a memo is
grounded in the engine's own facts and its list-pack citations, not in retrieved documents.

## Boundary and validation

- **What reaches the model is a minimised, structured fact set, not the request.** `_memo_facts`
  in `domain/screening_service.py` composes exactly the fields listed above, so the caller's
  identifier list and the analyst's free-text `context` never reach `NarrationPort` at all. Be
  precise about what that is and is not: this is minimisation by construction (principle P-04),
  NOT redaction. Party names, which are personal data, do reach the port, because a memo naming
  no party is useless. Redaction happens at the boundaries that persist or share the data
  instead: before the WORM audit write (`domain/screening_service.py` with `domain/pii.py`),
  before the review payload leaves the process (`adapters/_review_payload.py`, against every
  jurisdiction's rows because the console is a shared sink) and before any agent tool result
  returns (`agent/tools.py`). Anyone binding a real model here should decide, in their own DPIA,
  whether the party name may cross that boundary, and bind the `agent-guardrail-gateway` port if so.
- **Every draft is validated, and a bad one is discarded rather than repaired.**
  `domain/memo.py::is_grounded` compares every numeric token in the draft against
  `allowed_numbers`, the exact set the engine computed or already quoted in its own facts (so a
  legitimate `UN-1001` entry id is allowed and an invented `held 88%` is not). A draft that fails,
  or an adapter that raised, falls back to `build_memo`, which is grounded by construction, so a
  disposition never waits on generation and never inherits an ungrounded number. The result
  records which happened: `DispositionMemo.grounded` is `False` on the fallback path.
  `tests/unit/test_memo.py::test_an_ungrounded_draft_is_discarded_and_the_fallback_is_used` and
  `test_a_fabricated_number_is_not_grounded` are the standing gates, and the eval scores
  `memo_groundedness` at a 1.0 threshold over the golden set.
- **Nothing auto-executes (rule R8).** `requires_human_review` is always `True`, including on a
  proposed clear, and setting it and calling `ReviewRouterPort.route` is ONE act performed in the
  same request on the API, the CLI and the agent tool alike. A confirmed match maps to CRITICAL
  severity, which demands two approvals. `tests/unit/test_review_routing.py` asserts the routing
  rather than the flag; the managed router refuses rather than swallowing an escalation with no
  console configured, and the on-premises placeholder refuses rather than dropping it.

## Adapters and profiles

| Profile | Narration adapter | Behaviour |
|---|---|---|
| `local` | `adapters/local/narration.py` | Not a stub: returns the real grounded memo from `domain/memo.build_memo`, so the offline gate exercises the memo path and groundedness passes by construction. SDK-free. |
| `gcp` | `adapters/gcp/narration.py` | The managed seam. Pins the model id `gemini-3.5-flash` in `_MODEL` (a floating default is never used) and imports `google.genai` lazily, so the other profiles import the module with no SDK present. It currently RAISES `NotImplementedError`: the client, prompt and region wiring is a deployment concern that has not been done. |
| `onprem` | `adapters/onprem/narration.py` | Fail-fast placeholder for a client-hosted model. It refuses rather than returning empty prose, because a silent empty return would hide that the client's model was never wired. |

The same pattern applies to the one other managed seam on this journey,
`adapters/gcp/adverse_media.py`, which is a grounded-search backend rather than a generative
model and is likewise construction-only. Both are listed in
`managed_readiness.INCOMPLETE_MANAGED_OPERATIONS`, and `assert_managed_profile_ready` refuses a
`gcp` process while either is bound on the active path. Terraform's `managed_profile_implemented`
local should be set only when that tuple is empty.

The eval's promotion client also names `gemini-3.5-flash` when it asks the `model-quality-gate`
(`eval/run_eval.py::run_gate`), so the pinned id is stated in both places a promotion record
would read it.

## Remaining controls (TODO, repo owner)

- **Implement the managed adapter, then pin its version** (P-07). The model ID is pinned; the
  concrete model VERSION, the region, the prompt template, the decoding parameters and the safety
  settings are not, and none of them exist yet. Record them here when they do, and keep this card
  and `_MODEL` in step.
- **Budget, rate controls and a kill switch** (P-10, P-11). A per-tenant token budget, a request
  rate limit, a timeout and a circuit breaker on the narration call, and a switch that forces
  deterministic-only operation with the model disabled. The fallback path already makes that
  switch cheap: turning the model off degrades the memo prose and moves no figure.
- **Prompt-injection screening through `agent-guardrail-gateway`** (rule R1). Untrusted text reaches this service in
  the subject name, the payment-message fields and the analyst context. Only the first two can
  currently reach a narration prompt, but a guardrail port must be bound at the model boundary
  before one is wired, failing closed to deterministic-only when the screen is unavailable.
- **A managed-profile eval run through the `model-quality-gate`** (P-08, rule R5). The offline eval scores
  the deterministic pipeline: `memo_groundedness` currently measures a memo the engine itself
  wrote, which is grounded by construction and therefore not yet a test of a model. Register the
  bundle `sanctions-screening` with `model-quality-gate` and add a managed-profile run that scores
  real draft groundedness against the same golden cases.
- **Bind the prompt and response record to `agent-observability`** (rule R2). Today the WORM trail records the
  redacted screening summary and its citations, not the model exchange. A deployed model needs
  its inputs and outputs in the shared observability sink, with the span attributes staying
  structural as they are now.

Until these are complete, the system is safe to run offline: the deterministic engine plus the
deterministic memo builder produce the same bands, the same arithmetic and the same citations
that a managed deployment would, and the managed model path is not production-cleared.
