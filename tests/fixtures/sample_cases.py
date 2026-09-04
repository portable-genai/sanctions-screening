"""Canonical synthetic screening cases, shared by the unit and contract suites.

Every party is obviously fictional. One confirmed-match case, one clean case and one case that
carries a planted identifier are enough for the contract suite: parity means the SAME request
through every implementation, so a request has one home rather than being retyped per test.
"""

from __future__ import annotations

from sanctions_screening.domain.models import PartyKind, ScreeningRequest

#: The verified principal the tests attribute work to (never a client-asserted actor).
ACTOR = "analyst@bank.example"

#: A tenant partition, so the outbound-review assertions are not all on the empty string.
TENANT = "demo-bank"

#: A confirmed match: a designated entity (UN pack) whose owners resolve from the cdd-sow-research
#: fixture.
CONFIRMED_CASE = ScreeningRequest(
    subject="Volkov Metals OJSC (FICTIONAL)",
    kind=PartyKind.ENTITY,
    subject_id="acme",
)

#: A clean name: no list carries it, so the engine bands it clear and proposes a false positive.
#: Every disposition still routes: the system never clears a match on its own.
CLEAN_CASE = ScreeningRequest(
    subject="Beta Stationery Pte Ltd (FICTIONAL)",
    kind=PartyKind.ENTITY,
)

#: A planted identifier, so a redaction assertion has an independent literal to look for rather
#: than trusting the pattern pack to agree with itself.
PLANTED_NRIC = "S1234567D"

#: A second planted identifier, in the SUBJECT rather than the free-text context. A screen of a
#: natural person carries the name and the id in that field, and the two travel different routes:
#: the context reaches the audit summary, while the subject reaches the model's memo facts.
PLANTED_EMAIL = "kyc.desk@fictional.example"

#: A screen of a natural person whose SUBJECT key carries an id, for the model-boundary proof.
PII_SUBJECT_CASE = ScreeningRequest(
    subject=f"Dmitri Volkov (FICTIONAL) NRIC {PLANTED_NRIC}",
    kind=PartyKind.INDIVIDUAL,
    context=f"onboarding referral; queries to {PLANTED_EMAIL}",
)

#: A confirmed-match case that also carries personal data, for the redact-before-anything proofs.
PII_CASE = ScreeningRequest(
    subject="Dmitri Volkov (FICTIONAL)",
    kind=PartyKind.INDIVIDUAL,
    dob="1968-04-11",
    context=f"NRIC {PLANTED_NRIC} and mail ops@volkov.example on file",
)
