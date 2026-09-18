# Role Model

| Role | Responsibility |
|---|---|
| Product Owner | Intent, scope, acceptance criteria, product risk |
| Tech Owner | Architecture and general technical decisions |
| Security/Data Owner | Security, privacy, personal data, and applicable database risk |
| Implementer | Code and truthful implementation evidence |
| Reviewer | Independent correctness and regression review |
| Release Owner | Approves pipeline release-readiness evidence; separate production systems own deployment authorization |

Optional specialized roles include DB Owner, API Owner, Infrastructure Owner, and Payment Owner.

One person may hold multiple owner roles if organizational policy permits. AI agents may transcribe an actual user's standard approval but cannot decide for the user. Strict verifies human identities and independent review; standard does not claim either authentication or independent review from a chat receipt.

Standard unprotected T1/T2 permits an explicitly labelled local self-review instead
of independent human approval. An implementer/worker label (default `claude`) is
execution provenance, not a person's name or proof of independence. Standard
protected/T3/T4 work needs explicit scoped user decisions without identity/trust
setup. Strict retains signed role and independent-Reviewer checks.
