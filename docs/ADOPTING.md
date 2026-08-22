# Adopting this repo as your base

This repository (G2, the Sanctions Screening Copilot) is a **common base** that a bank, a
payments institution or another regulated firm forks to build its own **name and payment-message
screening desk**: a service that scores a party against sanctions and PEP list packs with a
deterministic fuzzy-match engine, screens the subject's beneficial owners from Doc1's resolved
ownership graph, drafts a disposition memo that may contain no number the engine did not compute,
and ROUTES every disposition to a human reviewer instead of clearing anything on its own. It
ships a reusable hexagonal core (a pure-stdlib domain, eight typed ports, three swappable adapter
families, a green offline gate) plus a fully worked screening vertical you can keep, retune or
replace with your own lists, thresholds and message flavours.

This guide is the step-by-step for making it yours. It has two halves: a **mechanical rebrand**
(one script) and the **human decisions** the script cannot make for you.

> Related reading: [`ARCHITECTURE.md`](../ARCHITECTURE.md) (the port table and the request
> pipeline), [`SPEC.md`](../SPEC.md) (the locked contracts), [`CONTRIBUTING.md`](../CONTRIBUTING.md)
> (the file-by-file touch list for a new port or adapter), [`COMPLIANCE.md`](../COMPLIANCE.md)
> (what is Covered, Partial and still owed), [`model-card.md`](model-card.md) (the model
> boundary as built), and the [`faq/`](faq/) directory.

---

## 1. What you keep vs what you rewrite

The core is hexagonal, and the boundary between reusable machinery and the screening vertical is
a physical module split: `domain/kernel.py` holds the vertical-neutral types (`Citation`,
`AuditEvent`, `Decision`, `Severity`, `utcnow` and the shared `StrEnum` taxonomies) and knows
nothing about screening, while `domain/models.py` holds only this vertical's artifacts. A fork
building a different vertical rewrites `models.py` and leaves `kernel.py` alone.

| Layer | Where | For your institution or vertical |
|---|---|---|
| **Vertical-neutral machinery** | `domain/kernel.py`, every Protocol in `ports/` (including `ports/identity.py`, the `VERIFIED` / `CLIENT_ASSERTED` / `UNIMPLEMENTED` vocabulary the exposure guard reads), the container wiring in `config.py`, `service_factory.py`, the eval harness mechanics in `eval/run_eval.py` | keep untouched |
| **Policy (your numbers)** | the `policy:` block in `config/settings.yaml` loaded into the frozen `MatchPolicy` by `domain/policy.py`: the four band thresholds (`weak_at`, `possible_at`, `strong_at`, `confirmed_at`), the four blend weights (`token_weight`, `name_part_weight`, `dob_weight`, `id_weight`) and `ownership_threshold_pct`; plus the `THRESHOLDS` dict in `eval/run_eval.py` | change deliberately, by configuration, not by editing the engine (see section 4) |
| **The vertical itself** | the artifact models in `domain/models.py` (`ScreeningRequest`, `ScreeningResult`, `PartyMatch`, `MatchBand`, `Recommendation`, `OwnershipGraph`, `DispositionMemo`), the list and guidance packs in `src/sanctions_screening/rulepacks/`, the message field map `_FIELD_MAP` in `domain/message_fields.py`, the corporate-suffix set `_CORP_SUFFIXES` in `domain/match_engine.py`, the jurisdiction selection in `domain/pii.py`, the local fixtures and the golden set in `eval/datasets/golden_cases.jsonl` | rewrite or reseed for your desk |

If your product is another screening or matching gate, the hexagon, the three profiles, the
deterministic-band pattern, the groundedness validator in `domain/memo.py`, the eval gate and the
Hrz7 review routing transfer directly. You replace the list packs and the message field map, and
retune the policy numbers.

Note what the engine deliberately does NOT branch on: `MatchEngine` reads a `MatchPolicy` and
knows no jurisdiction. A market that wants different bands edits configuration, not
`match_engine.py`.

## 2. Core-vs-adopter-owned files (so upstream merges stay mechanical)

Upstream keeps evolving these; avoid diverging from them so you can pull fixes cleanly:

- **Upstream-owned** (take our changes): `domain/kernel.py`, every Protocol in `ports/`,
  `config.py` (the `Container` and `DEFAULT_BINDINGS` shape), `service_factory.py`,
  `tests/contract/` including `canonical.py`, the eval harness mechanics in `eval/run_eval.py`,
  `adapters/_review_payload.py` and `adapters/_ubo_contract.py` (they encode a sibling's frozen
  contract, not your policy), `managed_readiness.py`, `api/app.py`'s security wiring, the
  `scripts/` demo mechanics, `infra/terraform/` module structure, and the CI workflows.
- **Adopter-owned** (yours; expect to edit): the *values* in `config/settings.yaml` (region,
  `policy:` block, review and Doc1 URLs), the list and guidance packs in `rulepacks/`, the
  jurisdiction tuple in `domain/pii.py`, `_FIELD_MAP` in `domain/message_fields.py`,
  `adapters/onprem/*` (the seams your own components land in), the fixtures in
  `tests/fixtures/sample_cases.py` and `src/sanctions_screening/_fixtures/`, the golden
  set in `eval/datasets/`, UI theming in `ui/`, your tfvars, and the jurisdiction rows plus the
  adopter-owned crosswalk section of [`COMPLIANCE.md`](../COMPLIANCE.md).

Track upstream via git tags; rebase your adopter-owned changes onto each release rather than
merging `main` continuously, so conflicts stay in the files you were told to expect.

## 3. The mechanical rebrand (one script)

`scripts/rename_fork.py` rewrites the python package name `sanctions_screening` (which
is ALSO this repo's console-script name, because the `[project.scripts]` entry point in
`pyproject.toml` is named after the package), the `SANCTIONS` environment prefix behind every
`SANCTIONS_PROFILE`-style variable, the distribution and resource id
`sanctions-screening`, and optionally the Terraform `name_prefix` default. Preview
first, then apply:

```bash
# Preview (writes nothing):
python scripts/rename_fork.py --package acme_screening_copilot \
    --env-prefix ACMESCREEN --resource acme-screening-copilot \
    --name-prefix acme-screen --dry-run

# Apply:
python scripts/rename_fork.py --package acme_screening_copilot \
    --env-prefix ACMESCREEN --resource acme-screening-copilot \
    --name-prefix acme-screen --yes

# Then recreate the environment (the distribution name changed) and prove it is green:
python3.12 -m venv .venv && source .venv/bin/activate
make install
make gate
```

Three things about the flags, because each one is a deliberate omission or scoping choice:

- There is **no `--cli` flag**. `--package` renames the console script too, and a second flag
  could only drift out of step with it.
- There is **no `--dist` flag**. `--resource` is one literal doing four jobs at once: the
  distribution name in `pyproject.toml`, the GitHub id in `[project.urls]`, the A2A agent-card
  name in `agent/agent_card.py`, and the Hrz4 eval bundle id `_BUNDLE` in `eval/run_eval.py`.
  They are the same string on purpose, so a fork's promotion record and its discovery card
  cannot disagree about which system they describe.
- `--name-prefix` is optional and is rewritten ONLY inside the `variable "name_prefix"` block in
  `infra/terraform/variables.tf` (default `g2-svc`). It is a short word, and a whole-tree
  replacement of a short word is how a rename script corrupts prose it was never asked to touch.

Add `--include-docs` to sweep Markdown prose too; a default run leaves it alone so the diff stays
reviewable. The script deliberately does NOT make the human decisions below.

## 4. The human decisions (the script can't make these)

1. **Region and residency.** The build is pinned to `asia-southeast1` (MAS / Singapore) in one
   render-time constant, `local.render_region` in `infra/terraform/render.tf.json`, which is what
   both Terraform variables default to. In your tfvars set BOTH `region` (the deploy region) and
   `allowed_regions` (the residency allowlist it is validated against) to your in-country region,
   and set `GCP_REGION` for the runtime, which reads it through `config/settings.yaml`. This is
   enforced, not merely described: the validation on `var.region` in `infra/terraform/variables.tf`
   fails at `terraform plan` when the effective region is outside the effective allowlist,
   `org_policy.tf` pins `constraints/gcp.resourceLocations` to that region's location group, and
   the CMEK key ring (`kms.tf`), the locked WORM audit bucket (`logging_worm.tf`) and the opt-in
   Cloud Run edge with its regional network endpoint group (`production_edge.tf`) are all created
   in `local.region`. `infra/terraform/production_edge.tftest.hcl` is the executable check
   (`residency_defaults_are_in_country` and `reject_region_outside_the_residency_allowlist`, both
   against a mocked provider, so they need no project and no credentials). The one piece still
   owed by the repo owner is build wiring: there is no `tf-check` make target and no `terraform`
   CI job, so today those runs only happen when somebody types
   `terraform -chdir=infra/terraform test` by hand. See [`runbook.md`](runbook.md).
2. **Identity and your IdP.** This repo owns no login flow. Under `gcp` the identity adapter
   (`adapters/gcp/identity.py`) verifies the IAP-injected assertion, checking the signature
   against IAP's own key set, the audience against the configured `SANCTIONS_IAP_AUDIENCE`, plus
   the expiry and the issuer; it is the one adapter that declares `VERIFIED`, which is the single
   flag the loopback exposure guard reads before it stands down. Under `local` you get seeded dev
   personas from `X-Dev-Persona` (offline demo and test only, declared `CLIENT_ASSERTED`, and the
   adapter refuses to construct unless `local` was chosen deliberately). Under `onprem` the
   placeholder declares `UNIMPLEMENTED` and refuses, which is the seam your own IdP lands in.
   Wire your issuer ON the deployed service and set the audience; `SANCTIONS_IAP_AUDIENCE` is
   three-state, and an unset or emptied audience refuses every caller rather than verifying
   without one. The Terraform `iap_audience` variable is filled in on a SECOND apply, from the
   `iap_audience` output, because the backend service is built from the Cloud Run service and a
   direct reference would be a cycle. See the "The IAP audience" section of
   [`runbook.md`](runbook.md).
3. **The policy numbers your compliance function owns.** They are configuration, not constants in
   the engine (practices check B4). The `policy:` block in `config/settings.yaml` is loaded by
   `domain.policy.load_match_policy` into a frozen `MatchPolicy`: the four band thresholds
   (`weak_at` 40, `possible_at` 60, `strong_at` 78, `confirmed_at` 90), the four blend weights
   that combine the token, name-part, date-of-birth and identifier sub-scores (`token_weight`
   0.55, `name_part_weight` 0.25, `dob_weight` 0.12, `id_weight` 0.08), and
   `ownership_threshold_pct` 25, the stake at or above which this screening treats a natural
   person from Doc1's graph as a beneficial owner. An absent key takes the shipped default, so you
   can retune one threshold without restating the rest, and `__post_init__` refuses a
   non-monotonic or out-of-range threshold set at load. Two safety properties are NOT tunable and
   should stay that way: the false-clear guard that forces an exact identifier match or an exact
   normalised-name match to the confirmed band, and the cross-kind cap that stops an individual
   confirming against an entity listing. Change the numbers deliberately, with your second line,
   and add a test that pins your values. Also set your own eval `THRESHOLDS` in
   `eval/run_eval.py`.
4. **Fixtures and reference data are synthetic, and the list packs are yours.** Everything shipped
   is obviously fictional: the six packs in `src/sanctions_screening/rulepacks/`
   (`ofac_sdn.json`, `un_consolidated.json`, `eu_consolidated.json`, `au_dfat.json`,
   `pep_list.json` and the `guidance.json` procedure notes), the captured Doc1 UBO graph in
   `src/sanctions_screening/_fixtures/doc1_ubo_graph.json`, the adverse-media corpus in
   `adapters/local/adverse_media.py`, and `tests/fixtures/sample_cases.py`. **The list packs are
   adopter-owned reference data.** This repo ships fictional stand-ins so the engine, the eval and
   the demo have something to screen against; it is not a list vendor, it does not refresh lists,
   and it makes no claim about the completeness or currency of anything in `rulepacks/`. Feed your
   own list provider's data through the same pack schema (`list_id` plus `entries`, validated by
   `domain.listpacks.validate_pack`, which raises rather than dropping a malformed pack, because a
   silently dropped entry is a screening gap that looks exactly like a clean screen), and decide
   where the refresh job lives, how a pack change is reviewed, and what your list-currency SLA is.
   Also retune `JURISDICTIONS` in `domain/pii.py` (shipped as `SG`, `HK`, `JP`, `AU`) and
   `_FIELD_MAP` in `domain/message_fields.py` for the message flavours your desk actually sees.
   **Do not run against real customer or counterparty data without your own legal, security and
   model-risk sign-off.**
5. **The eval golden set and its metrics.** `eval/datasets/golden_cases.jsonl` is a hand-written
   oracle: every `expected` field is written from the fixtures and the packs by hand, never copied
   from pipeline output, so a metric cannot score against the pipeline's own verdict. A fork
   inherits a green gate that measures the WRONG list set until you rebuild it. The six metrics
   and their thresholds (`recommendation_accuracy` 0.80, `no_false_clear` 1.0,
   `screening_coverage` 1.0, `pack_schema_validity` 1.0, `memo_groundedness` 1.0, `pii_safety`
   0.99) are in `THRESHOLDS`; the provable-red harness in `_assert_metrics_can_go_red` pins that
   each headline metric can still detect its own defect class, so keep a red case alongside every
   green one when you add a metric. `--mode smoke` is your offline pre-merge check; `--mode gate`
   asks Hrz4 and refuses to run off the managed profile.
6. **Deployment posture.** Review the Dockerfile (digest-pinned base, non-root uid 10001,
   `HEALTHCHECK` on `/healthz`), the loopback-by-default binding, and `infra/terraform/` before
   you expose anything. Note the fail-closed preflight in `managed_readiness.py`: while
   `INCOMPLETE_MANAGED_OPERATIONS` still names `narration.GeminiNarrationAdapter.draft_memo` and
   `adverse_media.GroundedAdverseMediaAdapter.search`, a managed process REFUSES to start rather
   than serving with a construction-only adapter on its primary journey. Implement and
   integration-test those two before you set Terraform's `managed_profile_implemented` local, and
   read [`model-card.md`](model-card.md) for what the model boundary does and does not currently
   cover.

## 5. Do not duplicate the platform

This repo is one system in a catalog of composable GRC systems. Several concerns it touches are
owned by sibling systems: integrate rather than rebuild them. The full map, with the shipped
status of each integration, is in [`faq/features-faq.md`](faq/features-faq.md); the status column
is authoritative in [`COMPLIANCE.md`](../COMPLIANCE.md).

- **Doc1** (the CDD and Source-of-Wealth agent) owns beneficial-ownership RESOLUTION. G2 does not
  resolve ownership; it consumes Doc1's frozen graph contract through `OwnershipGraphPort` and
  screens each resolved owner through the same match engine. Wired today: the managed adapter
  calls `resolve_ubo_graph` at `DOC1_A2A_URL`, the offline adapter replays a captured body through
  the SAME `parse_ubo_graph` reader, so a contract drift breaks the consumer test before it breaks
  production.
- **Hrz7** (the human-review and maker-checker console) owns review workflow and approvals. Wired
  today, and it is the reason `ReviewRouterPort` exists: rule R8 means an escalation is ROUTED,
  never merely flagged. Set `HRZ_HUMAN_REVIEW_URL`, supply the outbound `HRZ7_S2S_TOKEN` and
  `HRZ7_S2S_SIGNING_KEY`, and do not re-implement the console. The managed router refuses rather
  than swallowing an escalation when no console is configured.
- **Hrz4** (the AI-quality and model-risk gate) owns the promotion verdict. Half-wired: the client
  is here and registers the bundle `sanctions-screening`; you register that bundle,
  its metrics and its thresholds with Hrz4 so gate mode has an authority to ask.
- **Hrz5** (observability plus the immutable WORM audit sink) owns the enterprise trail. The
  in-repo hash-chained, externally anchored log is the offline stand-in; the managed tracer sends
  OTLP to the Hrz5 collector when `OTEL_EXPORTER_OTLP_ENDPOINT` is set. Binding the audit and
  prompt/response record to Hrz5 is still owed (rule R2).
- **Hrz3** (the agent registry) owns agent identity, versioning and entitlements. This repo
  publishes an A2A card at `/.well-known/agent-card.json` built from the same tool table the
  runtime binds; registering it with Hrz3 and taking entitlements from it is still owed (rule R4).
- **Hrz1** (the guardrail gateway) owns prompt-injection defence and output filtering. Not wired
  today, and honestly so: no model call currently executes on any profile. Bind a guardrail port
  before the narration adapter starts sending an analyst's free text to a model (rule R1).
- **Hrz2** (the governed knowledge base) owns ACL-aware grounded retrieval. Not used: this
  service grounds a memo in the engine's own facts and its list-pack citations, not in retrieval.
  A fork that adds a retrieval step takes on rule R3 and P-05 with it.
- **Rsk3** (the architecture and requirements validator) owns intake validation (rule R6). That is
  a process step at project intake, not a code control; record the reference in
  [`COMPLIANCE.md`](../COMPLIANCE.md) when you pass it.

G2's responsibility ends at the disposition: it screens, it cites, it narrates under validation,
it writes an already-redacted audit record, and it hands the case to a reviewer. It does not
approve, block a payment, file a report, freeze an account, or maintain the lists.

## 6. Adoption checklist

- [ ] Ran `scripts/rename_fork.py` with `--dry-run`, then `--yes`, recreated the venv, `make gate` green.
- [ ] Set `region` and `allowed_regions` in your tfvars and `GCP_REGION` for the runtime to your in-country region, and ran `terraform -chdir=infra/terraform test` at least once.
- [ ] Wired your IdP on the deployed service and set `SANCTIONS_IAP_AUDIENCE` from the second-apply `iap_audience` output (this repo owns no login flow).
- [ ] Replaced every list and guidance pack in `rulepacks/` with your own provider's data through the same pack schema, and decided who owns the refresh, the review and the currency SLA.
- [ ] Owned the `policy:` numbers (band thresholds, blend weights, `ownership_threshold_pct`) with your compliance function, and pinned them with a test.
- [ ] Retuned `JURISDICTIONS` in `domain/pii.py` and `_FIELD_MAP` in `domain/message_fields.py` for your markets and message flavours.
- [ ] Replaced every synthetic fixture (`_fixtures/doc1_ubo_graph.json`, the adverse-media corpus, `tests/fixtures/sample_cases.py`).
- [ ] Rebuilt `eval/datasets/golden_cases.jsonl` and the `THRESHOLDS` for your list set, keeping a provable-red case per metric.
- [ ] Wired `HRZ_HUMAN_REVIEW_URL` and `DOC1_A2A_URL`, and decided which other sibling systems you integrate vs stub.
- [ ] Reviewed the deploy posture (Dockerfile, `infra/terraform/`, bind address) and read `managed_readiness.py` before enabling the managed profile.
- [ ] Recorded your baseline upstream tag so you can take future fixes.
