# FAQ index

Answers to the questions different teams ask when evaluating, adopting or reviewing this
repository (G2, the Sanctions Screening Copilot) as a common base for a screening desk. Each
page is written for a specific audience; skim the one that matches your role.

| FAQ | For | Answers |
|---|---|---|
| [security-faq.md](security-faq.md) | AppSec / security review | server-verified identity, why the exposure guard reads the identity binding and not a credential, three-state configuration, where PII is redacted, secrets, supply chain, the anchored audit chain, the browser boundary |
| [portability-faq.md](portability-faq.md) | Architecture / cloud / exit planning | how real the no-lock-in claim is, the three profiles, the five-way port registration, the executable portability check, the sovereign exit, residency, open-format export |
| [features-faq.md](features-faq.md) | Product / business owner | what a disposition contains, what is deterministic vs narrated, payment-message and beneficial-owner screening, and the full "what this repo owns vs what it integrates" map |
| [adoption-faq.md](adoption-faq.md) | Engineering leads forking the repo | the rename script, taking upstream fixes, the kernel boundary, adding a port or adapter, retuning policy by configuration, whether the demo and CI survive a fork |
| [compliance-faq.md](compliance-faq.md) | Compliance / model risk / privacy | maker-checker and rule R8, redact-before-audit, reproducibility, the model-risk position, residency enforcement, what is still Partial, and what this system is not |

These FAQs deliberately do **not** re-document capabilities owned by sibling catalog systems.
Where a concern belongs to another system (Doc1 for beneficial-ownership resolution, Hrz1 for
guardrails, Hrz2 for governed retrieval, Hrz3 for the agent registry, Hrz4 for promotion, Hrz5
for the enterprise WORM sink and tracing, Hrz7 for the review console), the page names the
owning catalog id and explains the boundary rather than duplicating it. See
[features-faq.md](features-faq.md) for the full boundary map, and
[`../../COMPLIANCE.md`](../../COMPLIANCE.md) for the authoritative status of each integration.
