# Security FAQ

For an AppSec reviewer sizing up this repo (G2, the Sanctions Screening Copilot). It explains
what the attack surface is, which controls are enforced by a test rather than by convention,
what is deliberately out of scope, and where the evidence lives. Cross-references:
[`../../COMPLIANCE.md`](../../COMPLIANCE.md) (the principle-to-control map with the honest
status column), [`../runbook.md`](../runbook.md), [`../practices-audit.md`](../practices-audit.md).

## What does this system actually process?

A subject name plus the attributes that sharpen a match (kind, date of birth, identifiers,
jurisdiction), optionally a parsed payment message as ordered field pairs, optionally a subject
key for Doc1's ownership graph, and a free-text context an analyst may attach. It produces a
`ScreeningResult`: banded matches against the list packs, the beneficial owners screened, an
advisory adverse-media set, a disposition memo and the review reference the escalation was routed
to. Counterparty names and identifiers ARE personal data, so unlike a purely aggregate service
this repo carries a real redaction stage; see the redaction question below.

## How is identity handled? Can a caller spoof the actor?

No. The actor is resolved server-side on every route and the client-supplied one is discarded.
`api/app.py::get_principal` resolves a verified `Principal` through the bound `IdentityPort`, and
that principal is what becomes the audit actor and the review maker, never anything in the
request body. The three families differ in what they can honestly claim:

- `gcp`: `adapters/gcp/identity.py` verifies the IAP-injected assertion. It passes an explicit
  `audience=` (the configured `SANCTIONS_IAP_AUDIENCE`), because `audience=None` is documented as
  "the audience is not verified" and would accept any Google-signed OIDC token from any project;
  it pins `certs_url=` to IAP's own key set rather than google-auth's OAuth2 federated default;
  and it checks the issuer itself, which `verify_token` does not. Both the verifier call and the
  lazy import are wrapped, so `X-Goog-IAP-JWT-Assertion: not-a-jwt` from an uncredentialed peer
  gets a 401 and not a bare 500. `tests/unit/test_iap_identity.py` runs in every `make gate` and
  `tests/unit/test_iap_crypto_matrix.py` drives the REAL verifier over locally minted assertions.
- `local`: seeded dev personas picked with `X-Dev-Persona`. That is an unauthenticated grant and
  is labelled as one, and the adapter refuses to construct unless `local` was chosen deliberately
  rather than inherited from an absent variable.
- `onprem`: resolves nobody and refuses, which is the seam a client's own IdP lands in.

## Why is the exposure guard derived from the identity binding rather than from a credential?

Because a service credential authenticates a calling SERVICE and no end user, and deriving the
guard from it inverted the control: setting `SANCTIONS_S2S_TOKEN` switched the guard OFF for the
end-user routes it was protecting, and a LAN peer with no credential got the seeded approver
persona and a real screening decision. The guard now reads one thing: what the bound identity
adapter DECLARES about the end-user authentication it can provide
(`ports/identity.py`: `VERIFIED`, `CLIENT_ASSERTED`, `UNIMPLEMENTED`, with silence read as
`CLIENT_ASSERTED`, never as verified). `add_loopback_exposure_guard` is bound at MODULE scope in
`api/app.py`, because the Dockerfile `CMD` and `make run-api` serve the app OBJECT and a bound
that lives only in `main()` never runs in a shipped process.
`tests/unit/test_end_user_auth_posture.py` walks the guard's argument through the constants it
names and fails the build if a credential reappears at any depth;
`tests/unit/test_serving_path_exposure.py` is the standing gate on the module-scope binding.

## What happens if the profile variable goes missing in a deployment?

It fails visibly rather than serving a stranger. `SANCTIONS_PROFILE` resolves ONCE at import into
a `ProfileChoice` with three states: UNSET is NO CHOICE (the offline adapters still bind, but the
seeded personas are refused, no service-to-service scheme is selected, the dev CORS allowlist and
the `X-Dev-Persona` header are withdrawn, and the exposure guard refuses every route to a
non-loopback peer); SET-AND-EMPTY raises, so it cannot inherit the unset behaviour; SET-AND-UNKNOWN
raises, `Local` and `GCP` included. Both raises happen before the process can serve anything. The
choice is split into two derived postures on purpose: `exposure_profile` drives every RELAXATION
and reads `unconfigured` when nobody chose, while `bind_profile` drives the RESTRICTION and reads
`local`. Only `config.py` may read the variable, and
`tests/unit/test_profile_single_source.py` fails the build if another module re-derives it.

The same three-state rule applies to every security-relevant environment read, in both languages:
`tests/unit/test_three_state_env_reads.py` walks the AST of `src/`, `scripts/` and `eval/` and
fails on any two-state `os.environ.get` that is neither an exact-match comparison nor listed with
a written reason, and `ui/tests/three-state-env-reads.test.mjs` does the same for every shipped
`.mjs`, `.ts` and `.tsx`.

## Are the interactive API docs exposed in a deployed posture?

No. `/docs`, `/redoc` and `/openapi.json` are registered only when `exposure_profile` is the
deliberate `local`. Under `gcp` the loopback guard has stood down and the process binds every
interface, so those routes are ABSENT rather than guarded: a guard the profile has switched off
is no guard.

## Where is personal data redacted, and how do you know it happened?

At every boundary, not once. The screening service redacts the audit summary with the shared
`pii-kit` before the WORM write (`domain/screening_service.py`, using the row selection and
ORDER in `domain/pii.py`); `adapters/_review_payload.py` redacts subject, summary and every
citation snippet before the payload leaves the process, against EVERY jurisdiction's rows rather
than only this deployment's, because the Hrz7 console is a shared sink; and `agent/tools.py`
masks every string in a tool result, however deeply nested, because a tool result becomes a
model's context. `tests/unit/test_screening_service.py::test_pii_is_redacted_before_the_audit_write`
and `tests/unit/test_review_routing.py::test_the_payload_is_redacted_before_it_leaves_the_process`
are the standing gates, and `tests/unit/test_not_falsely_green.py::test_pii_safety_can_go_red`
proves the eval's safety metric can actually fail. Note the deliberate asymmetry: an API response
to the caller who supplied the text is NOT masked, because the caller already has that text; what
is protected is what reaches a durable record, a shared sink or a model.

## Are there secrets in the repo?

No literal secret material. `config/settings.yaml` holds environment variable NAMES and
non-secret defaults only, with `${VAR:-default}` interpolation resolved in three states;
`.env.example` documents the non-secret variables and `.env.secrets.example` documents the secret
NAMES with placeholders. The inbound and outbound credentials are deliberately distinct
variables: `SANCTIONS_S2S_TOKEN` authenticates callers INTO this service, while `HRZ7_S2S_TOKEN`
and `HRZ7_S2S_SIGNING_KEY` authenticate this service to the review console. Terraform mounts
secrets by immutable Secret Manager version and refuses `"latest"`, and it refuses a secret whose
environment variable name would shadow one the stack sets itself.

## What is the supply-chain posture?

Committed `requirements-dev.lock` and `requirements-gcp.lock`, installed with `--no-deps` by
`make install`, by CI and by the Dockerfile, with the four commons packages pinned in the lock to
the 40-character COMMIT each declared tag resolved to (a tag can be moved, so a tag pin lets what
installs change with no diff). `ruff` is pinned exactly, the base image is digest-pinned, Actions
are SHA-pinned, dependabot covers pip, docker, github-actions and npm, and `pip-audit` over both
locks is a hard CI failure. `tests/unit/test_repo_artifacts.py` asserts the three-way agreement
between `pyproject.toml`, the locks and the declared tags, offline.

The `hex-service-kit` pin is a security floor rather than a preference: the pinned release
checks the service-identity policy before the token, binds the exposure guard over both HTTP and
WebSocket scopes, and resolves every environment read in three states. Never move it
backwards.

## Is the audit trail tamper-evident?

Within honest limits, and the limits are the interesting part. The local sink is hash-chained AND
externally anchored: `audit_anchor_path` points at a file on a different volume that every append
writes the chain head to. The chain alone catches an in-place edit, an interior deletion or a
reorder; only the anchor catches a TRUNCATED TAIL, because a truncated chain still verifies
perfectly. Once the store and the anchor disagree the service refuses to append rather than
re-anchoring, so an ordinary write cannot launder a divergence.
`tests/unit/test_audit_anchor.py` proves both halves plus the control case where the same
truncation goes undetected without an anchor. In production the enterprise WORM store is Hrz5's
job and the managed adapter writes to a locked Cloud Logging bucket
(`infra/terraform/logging_worm.tf`, retention floor 180 days, lock irreversible).

## What about the browser surface?

`ui/` is an embeddable Next.js micro-frontend whose whole security boundary is one policy module
(`ui/lib/embed-policy.mjs`) and one server-side identity module (`ui/lib/server/identity.ts`).
The browser never asserts who it is: every client-supplied actor, tenant, role, ACL and
authorization header is discarded before forwarding, identity is resolved server-side, and the
service credential stays on the server. Framing and CORS are per-tenant allowlists that refuse a
wildcard however it is written, and an empty allowlist denies. `make drop-ui` removes the UI, its
dependabot ecosystem and its CI job together for a fork with no user-facing surface;
`tests/unit/test_ui_surface.py` holds that decision consistent in both directions. The row-level
detail is in the "Browser boundary" row of [`../../COMPLIANCE.md`](../../COMPLIANCE.md).

## What is explicitly out of scope for this repo?

Prompt-injection screening and output filtering (**Hrz1**, the guardrail gateway: not wired today,
and honestly so, because no model call currently executes on any profile), governed ACL-aware
retrieval (**Hrz2**), the agent registry that owns agent identity and entitlements (**Hrz3**), the
promotion and model-risk gate (**Hrz4**), the enterprise WORM audit and tracing sink (**Hrz5**),
the human-review and maker-checker console (**Hrz7**), and beneficial-ownership RESOLUTION
(**Doc1**, whose frozen graph contract this repo consumes rather than reimplements). This repo
integrates those through ports rather than re-implementing them; see
[features-faq.md](features-faq.md) for the full map and
[`../../COMPLIANCE.md`](../../COMPLIANCE.md) for which integrations are wired today.
