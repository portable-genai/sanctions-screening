# Compliance FAQ

For compliance, financial-crime governance, model-risk and privacy teams assessing G2, the
Sanctions Screening Copilot. Cross-references: [`../../COMPLIANCE.md`](../../COMPLIANCE.md) (the
full principle-to-control map, the status column and the adopter-owned regulator crosswalk),
[`../../SPEC.md`](../../SPEC.md) (the locked contracts),
[`../model-card.md`](../model-card.md), [`../practices-audit.md`](../practices-audit.md).

## Is this system making sanctions decisions autonomously?

No. It is decision SUPPORT, and the design makes that structural rather than a policy statement.
`requires_human_review` is always `True` on a `ScreeningResult`, including on a proposed clear:
the system never clears a match on its own. The escalation is not a local boolean either. Setting
the flag and calling `ReviewRouterPort.route` is one act, executed in the same request that
produced the result, so the escalation never depends on a later job that may not exist, and the
response carries a `review_ref` so a caller can distinguish a routed escalation from one that
stopped in this process. A confirmed match maps to CRITICAL severity, which the shared review
payload marks as demanding dual control (two approvals) rather than a single checker. The console
itself is **Hrz7**; this repo routes to it (dependency rule R8) and does not reimplement it.
`tests/unit/test_review_routing.py` asserts the routing, not the flag, and the on-premises
placeholder refuses rather than dropping an escalation, because a router that silently returned
would convert every consequential result into an unreviewed one.

The system also does not block a payment, freeze an account, file a regulatory report, or
maintain the lists. It produces a cited recommendation and hands the case to a human.

## How is personal data handled?

Counterparty names and identifiers ARE personal data, so this repo carries a real redaction
stage rather than declaring the concern out of scope. Redaction happens BEFORE every boundary,
not once:

- before the WORM audit write, in `domain/screening_service.py`, using the jurisdiction pattern
  selection and ORDER in `domain/pii.py` (shipped as `SG`, `HK`, `JP`, `AU`, over the shared
  `pii-kit`);
- before the review payload leaves the process, in `adapters/_review_payload.py`, and there
  against EVERY jurisdiction's rows rather than only this deployment's, because the Hrz7 console
  is a shared sink and a case filed in one market may quote another market's national id;
- before any tool result returns, in `agent/tools.py`, because a tool result becomes a model's
  context (principle P-04).

Redacting after the audit write would be too late, because the record is immutable. There is a
deliberate asymmetry: an API response to the caller who supplied the text is not masked, because
that caller already has the text; what is protected is what reaches a durable record, a shared
sink, or a model. The eval scores `pii_safety` two ways, with the pack scan and an independent
planted-literal oracle, at a 0.99 threshold, and
`tests/unit/test_not_falsely_green.py::test_pii_safety_can_go_red` proves that metric can
actually fail.

One thing to know for a DPIA: the span attributes on the screening trace are STRUCTURAL only
(the action, the actor, the party kind) and never the subject name, an identifier, the analyst's
free text or the drafted memo. A trace backend has no redaction stage, a wider read audience and
no retention rule written against a regulator's requirement, so content-shaped data reaching a
span would have left the boundary the redact calls exist to hold, and left it silently.

## How is the work auditable and reproducible?

Every screening writes an already-redacted, immutable `AuditEvent` carrying the decision, the
severity and the citation set, with the VERIFIED principal as the actor rather than anything in
the request body. Every claim carries a `Citation`: each list hit cites its listing, each media
item cites its source, the applicable guidance note is cited, and even a clean screen cites the
run itself so there is provenance for what was done. The consequential math is deterministic and
replayable, and `NameScore.arithmetic` keeps the actual sum (of the form
`(93.2x0.55 + 88.0x0.25) / 0.80 = 91.58`, with a note appended when a false-clear guard forced
the band) so a second line can recompute a band rather than trust it.
`tests/unit/test_match_engine.py::test_the_score_is_replayable` and
`tests/unit/test_screening_service.py::test_the_band_is_deterministic_across_runs` pin that.

The local trail is hash-chained AND externally anchored: the chain catches an edit, a deletion or
a reorder, while only the anchor catches a truncated tail, because a truncated chain still
verifies perfectly. Once store and anchor disagree the service refuses to append rather than
re-anchoring. In production the enterprise WORM store is **Hrz5**'s job, or a locked Cloud
Logging bucket (`infra/terraform/logging_worm.tf`, six-month retention floor, lock irreversible).

## What is the model-risk position?

Narrow and, today, conservative. A model has exactly one job in this system: narrating the
disposition memo behind `NarrationPort`. It produces no confidence figure, no band, no
recommendation and no ownership percentage, all of which come from pure stdlib code in
`domain/match_engine.py`. Any draft is validated by `domain/memo.py::is_grounded` and DISCARDED if
it contains a number the engine did not compute, falling back to the deterministic memo, which is
grounded by construction.

On the shipped build no model call executes on any profile: the offline adapter returns the
deterministic memo and the managed adapter is a construction-only seam. `managed_readiness.py`
names it, and the API preflight REFUSES to start a managed process while it is on the primary
journey, so "production ready" cannot become a label. [`../model-card.md`](../model-card.md)
records the boundary and the controls still owed (model id and version pinning, budget and rate
controls with a kill switch, a managed-profile eval run through the **Hrz4** gate, and
prompt-injection screening through **Hrz1**).

The offline eval gate (`eval/run_eval.py --mode smoke`) runs on every merge and scores six
metrics against a hand-written oracle, never against the pipeline's own verdict:
`recommendation_accuracy` at 0.80, `no_false_clear` at 1.0, `screening_coverage` at 1.0,
`pack_schema_validity` at 1.0, `memo_groundedness` at 1.0, and `pii_safety` at 0.99. `--mode gate`
delegates the promotion verdict to **Hrz4** and refuses to run off the managed profile.
Registering this repo's bundle and thresholds with Hrz4 is still owed (P-08, rule R5). Note
honestly that `memo_groundedness` currently measures a memo the engine itself wrote, which is
grounded by construction, so it is not yet a test of a model.

## Is data residency actually enforced, or just documented?

Enforced at deploy time. The region is one render-time constant shared by the runtime and
Terraform (`asia-southeast1` here). `infra/terraform/variables.tf` validates the effective region
against the residency allowlist at plan time, and the allowlist defaults to exactly the rendered
region; `org_policy.tf` pins `constraints/gcp.resourceLocations` to that region's location group
and forbids exportable service-account keys; and every regional resource is created in it (the
CMEK key ring, the locked WORM bucket, and the opt-in Cloud Run service with its regional network
endpoint group). `infra/terraform/production_edge.tftest.hcl` proves both directions against a
mocked provider: `residency_defaults_are_in_country` fails if any of those drifts off region, and
`reject_region_outside_the_residency_allowlist` fails if the allowlist stops refusing. The one
piece still owed is build wiring, since this repo has no `tf-check` make target and no
`terraform` CI job, so that suite runs only when somebody types it by hand. That is recorded
honestly in the P-03 row of [`../../COMPLIANCE.md`](../../COMPLIANCE.md).

## Which rows are still Partial or TODO, and what does that mean for go-live?

Read [`../../COMPLIANCE.md`](../../COMPLIANCE.md) rather than this page for the current list, and
read the status legend at the top of it: **Covered** means a test fails the build if the control
regresses, **Partial** means the in-repo half exists and the named deploy-time or platform half
does not yet, and **TODO (repo owner)** means NOT covered. The document is deliberately honest on
day one rather than complete on day one. The recurring theme in the open rows is platform
binding: the guardrail gateway (Hrz1), the shared observability and audit sink (Hrz5), the agent
registry (Hrz3) and the Hrz4 bundle registration are named rather than claimed. An adopter is
expected to record a risk acceptance for every row still Partial or TODO at go-live.

## Which regulators does this map to?

`COMPLIANCE.md` maps the catalog's own principles (P-01 to P-13) and platform dependency rules
(R1 to R8) to concrete controls with an evidence file per row, aligned in intent to MAS TRM, APRA
CPS 234 and CPS 230, HKMA and PDPA-class regimes. The mapping from those rows to a SPECIFIC
regulation, and the judgement that a control is SUFFICIENT for it, is explicitly adopter-owned:
it depends on the institution's risk appetite, its regulator, its licence conditions and its
existing control library. This repo does not make that claim on an adopter's behalf, and no row
should be quoted as regulatory assurance. Note in particular that sanctions-screening
effectiveness is not a code property: your list coverage, your threshold calibration, your
alert-to-review SLA and your independent testing are yours.

## Can we run it against real customer or counterparty data today?

Not without your own legal, security and model-risk sign-off. Everything shipped is obviously
fictional: the six list and guidance packs in `src/sanctions_screening/rulepacks/`, the
captured Doc1 ownership graph, the adverse-media corpus and the golden set, all using fictional
parties and `.example` domains. The packs in particular are adopter-owned reference data, not a
list feed: this repo is not a list vendor, does not refresh lists, and makes no claim about the
completeness or currency of what it ships. The prerequisites are the adoption checklist in
[`../ADOPTING.md`](../ADOPTING.md) section 6: your own list packs, your own policy numbers signed
off by your second line, your IdP wired, your residency region set, and your own golden set so
the eval measures your list set rather than the reference one.
