# Adoption FAQ

For an engineering lead forking G2, the Sanctions Screening Copilot, as an institution's
screening base. The step-by-step is [`../ADOPTING.md`](../ADOPTING.md); this page answers the
"will it hurt later?" questions. Cross-references:
[`../../CONTRIBUTING.md`](../../CONTRIBUTING.md), [`../../ARCHITECTURE.md`](../../ARCHITECTURE.md).

## How do I rebrand it for my organisation?

`python scripts/rename_fork.py` rewrites, in one pass: the python package name
`sanctions_screening`, the `SANCTIONS` environment prefix behind every
`SANCTIONS_PROFILE`-style variable, the distribution and resource id
`sanctions-screening`, and optionally the Terraform `name_prefix` default. Preview
with `--dry-run` (the default writes nothing anyway), apply with `--yes`, then recreate the venv,
`make install` and `make gate`.

Two flags you may expect are deliberately absent. There is no `--cli`: the `[project.scripts]`
entry point is named after the package, so `--package` renames the console script too and a
second flag could only drift out of step. There is no `--dist`: `--resource` is one literal doing
four jobs (the distribution name, the GitHub id in `[project.urls]`, the A2A agent-card name in
`agent/agent_card.py` and the Hrz4 eval bundle `_BUNDLE` in `eval/run_eval.py`), so a fork's
promotion record and its discovery card cannot disagree about which system they describe.
`--name-prefix` is scoped to the `variable "name_prefix"` block in
`infra/terraform/variables.tf`, and reads the current value from there rather than hardcoding
it, so a second rename still works.

## Is there a real kernel module I can keep untouched?

Yes, and the split is physical rather than described. `domain/kernel.py` holds the
vertical-neutral machinery (`Citation`, `AuditEvent`, `Decision`, `Severity`, `utcnow` and the
shared taxonomies) and knows nothing about screening; `domain/models.py` holds only this
vertical's artifacts (`ScreeningRequest`, `ScreeningResult`, `PartyMatch`, `MatchBand`,
`Recommendation`, `OwnershipGraph`, `DispositionMemo` and friends). A fork building a different
vertical rewrites `models.py` and leaves `kernel.py` alone. The full upstream-owned vs
adopter-owned list is [`../ADOPTING.md`](../ADOPTING.md) section 2.

## If several institutions fork this, how does each take upstream fixes?

Track upstream via git tags and rebase your adopter-owned changes onto each release rather than
merging `main` continuously, so conflicts stay in the files you were told to expect: the values
in `config/settings.yaml`, the packs in `rulepacks/`, `domain/pii.py`'s jurisdiction tuple,
`_FIELD_MAP` in `domain/message_fields.py`, `adapters/onprem/*`, the fixtures, the golden set,
`ui/` theming and your tfvars. Note that `adapters/_ubo_contract.py` and
`adapters/_review_payload.py` are upstream-owned even though they look local: they encode a
sibling system's frozen contract, not your policy.

## Can I retune the match thresholds without touching engine code?

Yes, and that is the shipped design (practices check B4). The `policy:` block in
`config/settings.yaml` is loaded by `domain.policy.load_match_policy` into a frozen `MatchPolicy`
dataclass: four band thresholds (`weak_at`, `possible_at`, `strong_at`, `confirmed_at`), four
blend weights (`token_weight`, `name_part_weight`, `dob_weight`, `id_weight`) and
`ownership_threshold_pct`. An absent key takes the shipped default, so you can retune one
threshold without restating the rest, and `__post_init__` refuses a non-monotonic or
out-of-range threshold set at load rather than at the first surprising band. `MatchEngine` reads
a `MatchPolicy` and branches on no jurisdiction, so a market with different bands is a
configuration change, never an engine fork.

Two engine behaviours are deliberately NOT configuration and should stay that way: the
false-clear guard (an exact identifier or exact normalised-name match is forced to the confirmed
band) and the cross-kind cap (an individual never confirms against an entity listing). Both are
pinned by `tests/unit/test_match_engine.py`. If you must change either, change the test in the
same commit so the change is visible in review.

## How do I add a new outbound dependency (a new port)?

There is a fixed touch list and a test that enforces it, so a missed step fails the build rather
than running with no enforcement. A port is registered in FIVE places: `ports/__init__.py`
(`PORT_PROTOCOLS`), `config.DEFAULT_BINDINGS`, a `Container` accessor, the `adapters:` block in
`config/settings.yaml`, and a `PortCase` in `tests/contract/canonical.py`. Then bind it in all
three families. `tests/contract/test_port_parity.py` asserts set equality across all five, in
both directions. See [`../../CONTRIBUTING.md`](../../CONTRIBUTING.md) for the walkthrough.

## How do I add a new adapter for an existing port?

The class goes under `adapters/<family>/` with one constructor shape, `Adapter(settings)`, and
any cloud import inside the method rather than at module scope, so the other two profiles import
it with no SDK installed. The same `module:Class` target goes in BOTH `config.DEFAULT_BINDINGS`
and `config/settings.yaml`, and `tests/unit/test_settings_file.py` fails the build if the two
disagree. Any new variable goes in `.env.example`. If the adapter is a construction-only seam on
the primary journey, add it to `INCOMPLETE_MANAGED_OPERATIONS` in `managed_readiness.py` so a
managed process refuses to start rather than serving a placeholder.

## Can I extend the taxonomies without editing engine code?

Yes. `PartyRole`, `PartyKind`, `MatchBand` and `Recommendation` are `LenientStrEnum` members from
the commons, so a member IS its wire value and the serialised JSON carries the enum string.
Adding a party role or a message flavour is a table entry: `_FIELD_MAP` in
`domain/message_fields.py` maps a field id to a role and a kind, and the ISO 20022 element names
and the SWIFT MT tags sit in the same table because a screening desk sees both on the same wire.
Extending `MatchBand` is the one that needs care, because `_BAND_ORDER` in `domain/models.py`
defines the severity ordering that `worst_band` and the review-floor comparison depend on.

## Will the demo rot after I diverge?

It is guarded, and the guard is inside the gate. A demo step exists in exactly two places,
`demo.STEPS` and `walkthrough.CHECKS`, and `tests/unit/test_demo_surface.py` holds the two equal,
so a narrated claim nobody verifies cannot exist. `make demo-selftest` runs the whole arc headless
and unattended, asserting at each step that the service actually reached the state the narration
claimed, and the hosted GitHub Actions check runs it along with `make portability`,
`make demo-static` and `make docs-check` on every push. When you add a step, put the numbers the
check reads in the step's `facts` dict rather than only in the rendered rows: a check that parses
prose breaks on a wording change.

## Does the gate run for my fork out of the box, with no credentials?

Yes, and that is a hard constraint rather than a happy accident. `make gate` is
`ruff check` plus `ruff format --check` plus `mypy src` plus `pytest -m 'not integration'` plus
the eval, and it is deliberately OFFLINE and credential-free: no cloud SDK, no project, no
network. If a change makes the gate need any of those, the change is wrong, not the gate.
Anything needing a live service lives in `tests/integration/` and is marked, and
`tests/unit/test_test_layout.py` fails the build if such a module is unmarked or if a test is
dropped into the `tests/` root. `make audit` (pip-audit over both locks) is the one step that
needs a network, which is why it is separate.

Note that the eval measures the REFERENCE list packs and golden set until you rebuild them. That
is an explicit adoption step, not a silent pass: a fork inherits a green gate that measures the
wrong list set until `eval/datasets/golden_cases.jsonl` and the `THRESHOLDS` are yours. Keep the
provable-red harness (`_assert_metrics_can_go_red`) alive as you go: a metric that cannot fail on
a crafted bad case is not a metric.

## What does adoption NOT get me, and who owns those pieces?

Forking this repo gets you the screening engine and the hexagon. It does not get you a review
console (**Hrz7**, which you point at and do not rebuild), a promotion authority (**Hrz4**, where
you register the eval bundle), an enterprise WORM audit and tracing sink (**Hrz5**), an agent
registry (**Hrz3**), a guardrail gateway (**Hrz1**), a governed knowledge base (**Hrz2**), or
beneficial-ownership resolution (**Doc1**, whose frozen graph contract this repo consumes). It
also does not get you list data: the packs in `rulepacks/` are fictional stand-ins and your
provider's feed, refresh cadence and currency SLA are yours. See
[features-faq.md](features-faq.md) for the full boundary map and
[`../../COMPLIANCE.md`](../../COMPLIANCE.md) for which integrations are wired today.
