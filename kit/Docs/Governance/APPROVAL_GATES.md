# Approval Gates

In scoped projects, reviews bind to Task or Phase completion evidence. STATE's
`full_run` field identifies that exact summary; protected/T3/T4 work expands to
project-wide checks and keeps every user-receipt (standard) or signature (strict) gate.
See [verification scopes](../Runbooks/VERIFICATION_SCOPES.md).

## Simple default, protected boundaries

Requirement clarification is separate from permission to work. Skipping duplicate
approval prompts never permits guessing material requirements. Resolve planning
questions under [CLARIFICATIONS.md](../Runbooks/CLARIFICATIONS.md); ordinary tasks
retain no user-approval gate, while actual missing requirement answers can block implementation.

User questions are decision boundaries, not a checklist at every implementation
step. Continue authorized ordinary work without repeated permission. Check existing
valid approvals first; `approval-request` reports NO_APPROVAL_REQUIRED or SATISFIED
when no new decision is needed. Present all currently required responsibilities in
one question per phase, retaining exact task/phase records. Explain the concrete
changed binding before requesting fresh consent. This changes prompting, not risk,
verification, protected approval authority or production permissions.

New adoption sets `approval_policy: "standard"`. Unprotected T0–T2 work does not
require human identities or an external trust file. T1/T2 still requires a local
review decision bound to the current revision, fingerprint, tree and Full summary.
The engine's `review` command and loop `reviewed` completion record this evidence;
it is labelled `self_review`, never human approval or independent review.

Standard protected/T3/T4 gates accept an explicit user approval receipt:
no human identity, signing key or external trust file is required. This is a local
transcription of the user's decision, not authenticated identity, proof of role
membership, or independently verified human review. Roles still describe the
decision responsibilities; one user can approve the presented responsibilities.
Existing valid signed records remain usable with their external trust.

`approval_policy: "strict"` requires signatures for all human gates, including
Reviewer for T1+ and Tech Owner design approval for ordinary T2. A missing policy
means legacy strict. Never silently downgrade an adopted project. Policy changes
invalidate prepared fingerprints and require explicit revision.

See [the approval receipt runbook](../Runbooks/APPROVALS.md) for request/record
commands, provenance requirements, withdrawal and explicit engine upgrades.

The following apply to user decisions, not AI self-review. Signature-only checks
(authenticated identity, independent signers and expiry) additionally apply to
strict and signed-record validation.

## Rules

- Record decision responsibilities, timestamp, scope, outcome, revision and fingerprint. Standard receipts also retain the actual user message, presented context and conversation reference; signed records retain the authenticated identity.
- Approval applies only to its stated scope, task revision, fingerprint, and phase.
- Review and release records also bind the current tree digest, prerequisite Full run ID, and SHA256 digest of that run's `summary.json` bytes.
- Any relevant source, task document, code tree, evidence summary, or revision change invalidates the applicable approval.
- Under strict, the trusted human Reviewer differs from the Implementer. Standard records a user's acceptance of the review evidence, not proof of an independent review. AI self-review or another AI review alone never satisfies a protected user-approval gate.
- The only accepted outcome is `APPROVED`. If conditions are present, every condition must already be `PASS` and reference evidence whose SHA256 matches. Pending conditions are not approval.
- Silence, issue assignment, merged code, or a green build does not imply a protected-decision approval.
- Approval of a design never grants review, a check exception, release readiness or production execution. Protected review/release require explicit phase-specific consent against the shown completion evidence only when no valid consent already covers that binding. Check actual prior messages and repair missing transcription before asking. Ordinary standard local review needs no user response. Exceptions require an exact check ID, reason and explicit user acceptance of that exception; they remain NOT_APPLICABLE, never PASS.
- Standard T4 release readiness requires a separate receipt covering Release Owner and all affected domain responsibilities. It does not claim multiple independent people. Strict T4 release retains at least two distinct human signers.
- Revoked or superseded approval must not be reused. Stop, preserve the old record and use `revise` to invalidate current approvals before obtaining fresh ones.

## Gate ownership

| Area | Required human authority |
|---|---|
| General T2 technical scope | Local decision in standard; Tech Owner in strict |
| Authentication/authorization/security | Security or designated domain owner |
| Personal data | Security/Data or Privacy owner |
| Database schema/migration | DB/Data owner |
| Public API/webhook contract | API/Tech owner |
| Payment/wallet/balance | Payment/Product owner plus technical owner |
| Infrastructure/DNS/CDN/WAF | Infrastructure owner |
| Release readiness record | Release Owner plus applicable domain owner |

Repository hosting controls should enforce these gates using branch protection, CODEOWNERS, environment approvals, and credentials unavailable to implementation agents. This repository does not invent account names for those controls.
