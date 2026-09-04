# Portability FAQ

For architecture, cloud and exit-planning reviewers who want to know how real the "no lock-in"
claim is in G2, the Sanctions Screening Copilot, and how an off-cloud or sovereign exit would
actually work. Cross-references: [`../../ARCHITECTURE.md`](../../ARCHITECTURE.md),
[`../onprem-migration.md`](../onprem-migration.md), [`../runbook.md`](../runbook.md).

## What is the no-lock-in claim, concretely?

`src/sanctions_screening/domain/` is pure standard library: no cloud SDK, no web
framework, no HTTP client. The whole consequential path lives there. `match_engine.py` computes
the confidence and the band with `difflib`, `re` and `unicodedata`; `memo.py` builds and validates
the disposition memo; `message_fields.py` extracts parties from a payment message with a data
table; `listpacks.py` reads the packs with stdlib `json` rather than YAML precisely so the domain
imports no third-party parser; `policy.py` holds the adopter's numbers in a frozen dataclass.
Everything outside is behind a `@runtime_checkable` Protocol in `ports/` and selected by one
setting. This is enforced, not asserted: `tests/unit/test_core_purity.py` scans the domain's
imports, and its own control case
(`test_the_scan_can_see_a_violation`) proves the scanner can go red.

## What are the three profiles?

`SANCTIONS_PROFILE` selects the whole adapter stack for all eight ports at once:

- **`local`** (the dev, test and CI default) is a real, working, SDK-free offline stack, not a
  pile of stubs. The audit sink is a hash-chained SQLite WORM log from the commons, identity is
  seeded dev personas, the review router enqueues into the review kit's inspectable outbox, the
  ownership adapter replays a captured `cdd-sow-research` graph, adverse media answers from a small fictional
  corpus, and narration returns the real deterministic memo from `domain/memo.build_memo`.
- **`gcp`** is the managed stack: Cloud Logging WORM, IAP identity, the `human-review-console` service intake over
  S2S, `cdd-sow-research` over A2A, and the managed tracer. Every cloud SDK import is LAZY, inside the method,
  so the other two profiles import these modules with no SDK installed at all.
- **`onprem`** is fail-fast placeholders that satisfy the same Protocols and RAISE. That is the
  reversibility proof (P-12) and it is deliberate: a review router that silently returned would
  convert every consequential result into an unreviewed one, which is worse than a missing
  feature. Tracing is the one exception, absent rather than fatal, because it is not essential to
  correctness.

Profile selection is an exact lookup, so a missing `local` or `onprem` binding never inherits
`gcp` and cannot import a managed SDK or change data custody silently.

## How do you stop a port from quietly escaping the contract?

A port is registered in FIVE places: `ports/__init__.py` (`PORT_PROTOCOLS`),
`config.DEFAULT_BINDINGS`, a `Container` accessor, the `adapters:` block in
`config/settings.yaml`, and a `PortCase` in `tests/contract/canonical.py`.
`tests/contract/test_port_parity.py` asserts set equality across all five, in both directions, so
a port that is bound but unregistered (or registered but unbound) fails the build instead of
running with no enforcement. `tests/contract/test_behavioral_parity.py` then proves the same
canonical request behaves the same at each family's boundary. The full touch list is in
[`../../CONTRIBUTING.md`](../../CONTRIBUTING.md).

## Is the portability claim tested, or just asserted?

Tested, and bounded. `make portability` runs `scripts/portability_demo.py` offline and exits
non-zero on any failed claim, with a pass or fail printed per named check: every port bound in
every profile, every adapter constructing and conforming to its Protocol, the offline family
ANSWERING, the exit family REFUSING, in-place rewrite detection, anchored truncation detection
with its control case, the trail surviving export and reload outside this codebase, and no cloud
SDK imported. It also prints what it does NOT prove, which is the part worth reading. The demo
gate workflow runs it on every push.

## How would a sovereign or on-prem exit actually go?

The `onprem` family is the scaffold, and each raising placeholder marks a seam where a client
supplies its own component: its IdP (`adapters/onprem/identity.py`), its audit store, its review
and approval queue, its ownership source, its adverse-media source, its model host. Because the
domain never changes, the exit is an adapter exercise rather than a rewrite: the bands, the
arithmetic, the citations and the escalation rule are identical on the way out. The step list is
in [`../onprem-migration.md`](../onprem-migration.md).

Two seams deserve advance thought. The ownership source is `cdd-sow-research`'s frozen contract, parsed by the
shared `adapters/_ubo_contract.py::parse_ubo_graph` that BOTH the managed and offline adapters
use, so whatever you bind on premises must produce that shape rather than a private one. And the
review router must not be stubbed to return quietly: rule R8 exists because a flag nobody reads
is auto-execution with extra steps.

## How is data residency handled?

The region is one render-time constant, `local.render_region` in
`infra/terraform/render.tf.json` (`asia-southeast1` here), that both the runtime and Terraform
share. It is enforced at deploy time rather than described: the validation on `var.region` in
`infra/terraform/variables.tf` fails at plan time when the effective region is outside the
effective residency allowlist, `org_policy.tf` pins `constraints/gcp.resourceLocations` to that
region's location group and forbids exportable service-account keys, and every regional resource
(the CMEK key ring in `kms.tf`, the locked WORM bucket in `logging_worm.tf`, the opt-in Cloud Run
service and its regional network endpoint group in `production_edge.tf`) is created in it.
`infra/terraform/production_edge.tftest.hcl` is the executable check and runs against a mocked
provider, so it needs no project and no credentials. Moving to a second region is a tfvars change
plus a residency review, not a fork. The one gap is build wiring: this repo has no `tf-check`
make target and no `terraform` CI job, so that test suite runs only when somebody types
`terraform -chdir=infra/terraform test`.

## Can the data be exported in an open format?

Yes. The audit trail exports to and restores from JSON Lines through the commons
`HashChainedAuditLog`, so the exit is a file copy and the chain can be re-verified elsewhere;
`scripts/portability_demo.py` exercises exactly that as one of its named checks. The screening
artifacts serialise through `hex_service_kit.serialization.to_jsonable`, which is what the agent
tool results and the A2A card are built from, so a result is plain JSON with no bespoke reader.

## What is honestly NOT portable, and what does this repo not own?

Three things, stated rather than glossed:

- **Tamper-evidence is scoped to what the local sink can prove.** The in-repo chain plus anchor
  detects edits, deletions, reorders and truncation, but production WORM custody is `agent-observability`'s
  job (or a locked Cloud Logging bucket), and this repo's managed adapter writes to it rather
  than replacing it.
- **The list packs are reference data, not a portable asset of this repo.** The six packs in
  `rulepacks/` are obviously fictional stand-ins so the engine and the eval have something to
  screen. Your list provider's data, its refresh cadence and its currency SLA are adopter-owned;
  see [`../ADOPTING.md`](../ADOPTING.md) section 4.
- **The managed profile is not production-cleared today.** `managed_readiness.py` names two
  construction-only adapters (`narration.GeminiNarrationAdapter.draft_memo` and
  `adverse_media.GroundedAdverseMediaAdapter.search`) and the API preflight REFUSES to start a
  managed process while either is on the primary journey. That is the honest state, not a
  portability defect: the offline profile is the complete one.

Beneficial-ownership resolution belongs to `cdd-sow-research`, the promotion verdict to `model-quality-gate`, the review
console to `human-review-console`, the agent registry to `agent-registry`, and guardrails to `agent-guardrail-gateway`. Porting this
service does not port those; see [features-faq.md](features-faq.md) for the boundary.
