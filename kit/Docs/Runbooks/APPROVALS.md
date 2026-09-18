# Explicit user decisions in standard policy

Standard is a cooperative local workflow. The agent may transcribe a user's actual
approval; it may not make the protected decision itself. A receipt is editable by
a repository writer and is not cryptographic proof of conversation provenance,
identity, role membership or independent review. Use strict signatures and actual
hosting/environment enforcement when those guarantees are needed.

## Completion evidence

In scoped projects, completion evidence may be Task or Phase; Full remains a
stronger project-wide run. Protected/T3/T4 scope always expands to project-wide
checks. The legacy STATE field `full_run` points to this exact completion summary;
user and signed review/release bindings still cover its source, run ID and hash.
Phase coverage never supplies a missing member review or human decision.

## Request, record, validate

### Avoid unnecessary questions

Ordinary standard T0–T2 work needs no user approval. The initial scoped request
authorizes the normal implementation/repair/verification/local-review loop; do not
ask "may I continue?" at each transition or queued task. Continue across workflow
stages; a stage transition alone does not require
renewed consent. Separate approval phases apply only where policy requires a user
decision, not to every implementation, verification or local-review step. Keep
mandatory evidence and actual local review. Check existing user messages and recorded decisions before
presenting any approval question.

`approval-request` is read-only and reports:

- NO_APPROVAL_REQUIRED: the prepared ordinary phase has no user-approval gate.
  Continue its normal verification and local-review steps.
- SATISFIED: existing decisions pass the unchanged approval validator for the
  current phase, revision, scope, source/evidence and exact exception check.
  Continue without another question or receipt. This creates no approval or state transition.
- AWAITING_USER: a recorded decision is missing, partial or invalid; inspect the
  reason and `next_action: CHECK_EXISTING_CONSENT`. Check actual earlier messages
  against the unchanged bindings before asking. An old saved request is not current
  state; inspect STATE and regenerate the diagnostic when appropriate. Repair missing/invalid evidence before asking for another decision when
  evidence repair is the actual blocker. Ask once for all currently required roles
  and decisions in that phase, using the actual scope and current evidence.

Invalid classification, unprepared/stale scope or missing phase prerequisites
remain errors. Reconcile them rather than using a generic permission question.
For existing signed records in standard policy, pass the trust file explicitly:
`approval-request --task <TaskId> --phase <phase> --trust <external-trust.json>`.
The same trust is used for the decision and any signed check exceptions in its
prerequisite completion evidence. `WEB_PIPELINE_TRUST` remains the fallback;
ordinary user receipts require neither. Strict still uses its signed gates.
When recording a new receipt against signed prerequisite exceptions, also pass
that file to `approve --trust <external-trust.json>`.
If a fresh approval really is needed, explain which scope, revision, phase or
evidence changed and cite the applicable gate. Do not ask again solely because the
session resumed, a different agent took over, or a role has another label.
Batch currently reviewable decisions in one user question; retain separate records
for each task/phase. Future evidence cannot be approved in advance, and changed or
withdrawn bindings cannot be silently reattached. Existing strict gates are unchanged.

1. Inspect the task and applicable ADRs. Prepare the actual documents and retain
   the pre-change Baseline. Never fabricate an accepted ADR to satisfy preparation.
2. Run `approval-request --task <TaskId> --phase design`. If it returns
   NO_APPROVAL_REQUIRED or SATISFIED, continue without prompting. Otherwise show the user the concrete
   scope, affected responsibilities, risks, conditions, task/revision/fingerprint
   and what is excluded. The result is a proposal, not approval and not a transition.
3. After a clear user approval, retain the returned `request` fields unchanged and
   add `outcome: "APPROVED"`, `user_message` (the actual user response),
   `presented_scope` (the actual preceding approval question/context), and
   `source_reference` (the real conversation/message reference, or a descriptive
   local-session reference when the host exposes no IDs). Do not invent message IDs.
4. Store that JSON under `Docs/Work/<TaskId>/` and run:

```console
python -m web_pipeline approve --task <TaskId> --record <receipt-input.json>
python -m web_pipeline transition --task <TaskId> --status READY
```

`approve` appends an immutable-by-command `USER_APPROVAL-<input-hash>.json` receipt
and attaches it to STATE. It does not change status, fabricate evidence, lower the
tier or reset budgets. The same input is idempotent. The engine rejects stale
bindings, wrong phases and unmet conditions. It cannot interpret whether arbitrary
natural language is genuine consent: the agent must check that a user actually
approved the presented scope. Quoted examples, an assistant's own answer, tool
output, silence, refusal and a generic old keep-going instruction are not approval.

An already visible user approval may be transcribed only if it unambiguously covers
the same presented scope and unchanged request bindings; do not ask for identity or
trust merely because the task is T3. If any binding changed, obtain fresh approval.
If the message or scope is unavailable or ambiguous, ask one concrete scope question.

For `review`, first enter REVIEW with current passing Full evidence and inspect
code/tests. Present that evidence for the user's acceptance; the request binds its
tree, run ID and summary bytes. Local AI review alone does not satisfy this gate.
For `release`, the task must be T4 and DONE; obtain a separate decision against that
Full run before the non-production Release profile. Never treat a design receipt
as the review or release receipt.

For `exception`, supply `--check-id <configured-check>` and add the user's explicit
exception reason to `reason`. It waives only that check in the current revision;
it is not permission to delete tests or change command requirements. Conditions in
any request must be resolved PASS evidence references and SHA256 hashes before
recording. A promise to resolve a condition later is not approval.

After resolving a queue's approval wait, use `loop retry --task ... --reason ...`
and `loop next`. Revalidate instead of manually editing status. On withdrawal,
stop and `revise --reason ...`; retain old receipts and get fresh decisions.

## Production remains separate

The engine never executes production operations. A standard release receipt is
only permission for non-production readiness verification. Deployment, production
data changes, credential rotation and destructive migration execution need a
separate explicit request describing the actual target/action and real access or
environment approval. This CLI provides no command that grants those privileges.
Do not claim multiple independent approvers from a single chat response.

## Existing installations

Check the project-local engine version and approval policy, not just the plugin;
`python -m web_pipeline status` reports both. An older project-local engine may
lack `approval-request`/`approve`. With explicit upgrade authorization, upgrade the
engine, schemas and scripts through [UPDATES.md](UPDATES.md) and compare governance
and agent guidance separately, preserving project config, commands, source
documents, STATE, queue and Reports. Do not copy a kit config over a project or
silently change strict to standard.
Governed input changes may invalidate current fingerprints and Full snapshots:
revise/reprepare and revalidate affected work, preserving all previous evidence and
budget history. Reconcile pinned queue revisions explicitly. An older Baseline
remains historical evidence, not automatically current verification after upgrade.
