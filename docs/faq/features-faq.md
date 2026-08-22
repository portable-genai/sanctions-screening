# Features FAQ

For product and business owners: what G2, the Sanctions Screening Copilot, actually produces,
what is computed deterministically vs narrated, and, importantly, where its responsibilities
**stop** and a sibling catalog system takes over. Cross-references:
[`../../README.md`](../../README.md), [`../../DEMO.md`](../../DEMO.md),
[`../../ARCHITECTURE.md`](../../ARCHITECTURE.md), [`../model-card.md`](../model-card.md).

## What does G2 actually produce?

A cited **screening disposition**. From a subject name (plus optionally its kind, date of birth,
identifiers, jurisdiction, a parsed payment message and a Doc1 ownership key) it produces a
`ScreeningResult` carrying:

- the **matches** against the sanctions and PEP list packs, each with a confidence figure from
  0 to 100, a band (`clear`, `weak`, `possible`, `strong`, `confirmed`) and the arithmetic that
  produced it, kept in `NameScore.arithmetic` so a reviewer can read the sum rather than trust it;
- the **parties extracted from the payment message**, each screened in its own right;
- the **beneficial owners** resolved from Doc1's ownership graph, each screened through the same
  engine, so an owner on a list is caught even when the payer name is clean;
- an **adverse-media** set, advisory only;
- a **disposition memo**, and a proposed disposition (`false_positive`, `needs_info`,
  `true_match`) that is a recommendation and never an action;
- a **citation** set: every list hit cites its listing, every media item cites its source, the
  applicable guidance note is cited, and even a clean screen cites the run itself so there is
  provenance for what was done;
- the **review reference** the escalation was routed to.

## What is deterministic, and what does a model do?

The consequential path is deterministic, replayable pure stdlib. `domain/match_engine.py` owns
the whole of it: name normalisation (accent folding, transliteration to ASCII, casefolding,
punctuation stripping, corporate-form tokens dropped so "Ltd" against "Limited" is not a
mismatch), the four sub-scores (token similarity, name-part overlap, date of birth, identifier),
the weighted blend, the band, and the proposed recommendation. `domain/policy.py` holds the
thresholds and weights as the adopter's configuration, so a market that wants different bands
edits `config/settings.yaml` and not the engine.

A model has exactly one job in this system: narrating the disposition memo, behind
`NarrationPort`. It restates figures the engine already computed and adds nothing consequential,
and `domain/memo.py::is_grounded` rejects any draft containing a number the engine did not
produce; a rejected draft is DISCARDED and the deterministic memo is used instead, so the output
never degrades below a real, cited memo.
`tests/unit/test_memo.py::test_the_numbers_are_identical_with_the_generation_adapter_stubbed_out`
pins that. On today's shipped build no model call executes on any profile: the offline adapter
returns the deterministic memo and the managed adapter is a construction-only seam that refuses.
See [`../model-card.md`](../model-card.md) for the boundary in full.

Two safety properties of the engine are worth knowing because they are not tunable. An exact
identifier match, or an exact normalised-name match that no date of birth contradicts, is forced
to at least the confirmed band, so a genuinely designated party can never band as clear because
one sub-score happened to be low. And an individual never confirms against an entity listing, or
the reverse, because a shared token is not a shared party.
`tests/unit/test_match_engine.py` holds both.

## Is anything auto-cleared, auto-blocked, or auto-reported?

No, in both directions, and this is the deliberate design. `requires_human_review` is ALWAYS
`True` on a `ScreeningResult`, including on a proposed clear: the system never clears a match on
its own. The escalation is not a per-repo boolean either. Setting the flag and calling
`ReviewRouterPort.route` is one act, performed in the same request that produced the result, on
the API, the CLI and the agent tool alike (dependency rule R8), and the response carries a
`review_ref` so a caller can tell a routed escalation from one that stopped here. A confirmed
match maps to CRITICAL severity, which demands two approvals rather than one.
`tests/unit/test_review_routing.py` is the standing gate.

G2 also does not block a payment, freeze an account, file a report to a regulator, or maintain
the lists. It screens, it cites, it narrates under validation, it writes an already-redacted
audit record, and it hands the case to a reviewer.

## What happens when an enrichment source is unavailable?

Each degrades in the way that matches its meaning, rather than uniformly. Adverse media is
advisory, so a failure drops the enrichment and never changes a band. An ownership source that
is configured but unreachable degrades with an explicit `ownership_unresolved` flag, because
serving the name screening without the ownership enrichment is serving LESS, not serving
less-verified. A confirmed refusal (the on-premises placeholder) is re-raised rather than
swallowed, so an on-premises deployment must wire its own source rather than silently screening
no owners. A truncated graph sets `ownership_truncated`, because the percentages are then a
floor and presenting them as complete would be misreporting.

## Which capabilities does this repo own vs integrate?

G2 owns the screening domain: the match engine, the band policy, the payment-message party
extraction, the pack schema and loader, the memo groundedness rule, and the disposition itself.
Everything below is owned by a sibling catalog system. Do not rebuild these in a fork; the
authoritative status of each row is the matching row in
[`../../COMPLIANCE.md`](../../COMPLIANCE.md).

| Concern | Owned by | G2's role, today |
|---|---|---|
| Beneficial-ownership resolution (the UBO graph) | **Doc1**, the CDD and Source-of-Wealth agent | consumes it through `OwnershipGraphPort` and screens each resolved owner; the managed adapter calls Doc1's A2A `resolve_ubo_graph`, the offline adapter replays a captured body through the SAME reader, so a contract drift breaks a test here first |
| Human review, maker-checker, dual control | **Hrz7**, the human-review console | routes every disposition to it over the shared review kit (rule R8); wired, and the managed router refuses rather than swallowing an escalation with no console configured |
| AI-quality, eval and promotion gate | **Hrz4** | registers the bundle `sanctions-screening`; `--mode gate` asks Hrz4 for the verdict and refuses to run off the managed profile. Registering the bundle and its thresholds with Hrz4 is still owed |
| Observability, tracing and the enterprise WORM audit sink | **Hrz5** | the managed tracer sends OTLP to the Hrz5 collector when configured; the in-repo hash-chained, externally anchored log is the offline stand-in. Binding the audit record to Hrz5 is still owed (rule R2) |
| Agent registry, versioning, identity, entitlements | **Hrz3** | publishes an A2A card at `/.well-known/agent-card.json` built from the same tool table the runtime binds. Registering it with Hrz3 is still owed (rule R4) |
| Runtime guardrail: prompt-injection defence, output screening | **Hrz1** | not wired, and honestly so: no model call executes today. It becomes mandatory the moment the narration adapter sends an analyst's free text to a model (rule R1) |
| Governed, ACL-aware knowledge base with citations | **Hrz2** | not used: a memo is grounded in the engine's own facts and the list-pack citations, not in retrieval. A fork that adds retrieval takes on rule R3 and P-05 with it |
| Architecture and requirements validation at intake | **Rsk3** | a process step at project intake, not a code control (rule R6) |
| Customer-facing marketing and financial-promotions claim checking | **Mkt6** | not applicable: this service produces no customer-facing output (rule R7, principle P-13) |

So the review console, the eval platform, the audit sink, the registry, the guardrail gateway and
the ownership resolver are **dependencies**, not features of this repo.

## Where do the list packs come from?

They are **adopter-owned reference data**, and the six packs shipped in
`src/sanctions_screening/rulepacks/` (`ofac_sdn.json`, `un_consolidated.json`,
`eu_consolidated.json`, `au_dfat.json`, `pep_list.json`, and the `guidance.json` procedure notes)
are obviously fictional stand-ins so the engine, the eval and the demo have something to screen
against. This repo is not a list vendor: it does not refresh lists and makes no claim about the
completeness or currency of anything in `rulepacks/`. Packs are DATA rather than code on purpose,
so a list update is a reviewed pack edit and not a code change, and `domain/listpacks.py` refuses
a malformed pack loudly rather than contributing partial data, because a silently dropped entry
is a screening gap that looks exactly like a clean screen. Feeding your provider's data through
the same schema, and owning the refresh cadence and currency SLA, is an adoption step:
[`../ADOPTING.md`](../ADOPTING.md) section 4.

## How many ways can the capability be reached?

Five, and they behave the same because they share the domain service rather than reimplementing
it: the FastAPI app (`POST /v1/screen`), the argparse CLI (`sanctions_screening screen`),
the agent tools advertised on the A2A card (`screen_name`, `screen_payment_message`,
`list_disposition_queue`, `verify_audit_trail`), the embeddable micro-frontend in `ui/`, and the
eval harness. Each routes an escalated result to human review in the same call that produced it,
so rule R8 does not hold on four surfaces out of five. Tool results are additionally masked for
personal data before they return, because a tool result becomes a model's context.

## How do I see it working?

`make demo` runs a presenter-paced, eight-step walkthrough against the real services offline: the
service binding, a routine case, a consequential case routed to review, a case carrying personal
data masked before the audit write, the reviewer's queue, the audit trail, a TAMPERED record the
chain names, and the exit profile refusing loudly. Every narrated claim is asserted, so a step
that stops being true exits non-zero rather than surfacing in front of an audience.
`make demo-selftest` runs the same arc headless, `make demo-static` renders the panels to static
HTML for screenshots, and `make portability` runs the executable portability claim. Everything is
offline and uses obviously fictional parties and `.example` domains. See
[`../../DEMO.md`](../../DEMO.md).
