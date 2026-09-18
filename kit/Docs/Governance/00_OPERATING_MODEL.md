# Operating Model

## Principle

AI implementation is not completion. A change is complete only when implementation, verification, evidence, review, and required approval are all complete.

The model has five layers:

| Layer | Governing question | Mechanism |
|---|---|---|
| Intent | What are we building and why? | Product spec, feature spec, acceptance criteria |
| Guidance | How should an agent work? | `PIPELINE.md` (imported by `CLAUDE.md`), plans, runbooks |
| Verification | Does it actually work? | Unit, contract, integration, E2E, browser, build, smoke |
| Enforcement | Can the boundary be bypassed? | CI, protected branches, CODEOWNERS, separated database/deploy credentials |
| Accountability | Who decided and approved? | ADR, risk acceptance, review and release records |

Guidance without enforcement is not control. A production credential unavailable to the AI runtime is stronger than an instruction not to use it.

## Operating invariants

1. `WEB-INV-01`: A check that was not executed is not PASS. Valid outcomes are PASS, FAIL, NOT_RUN, BLOCKED, NOT_APPLICABLE, and INCONCLUSIVE.
2. `WEB-INV-02`: NOT_APPLICABLE requires a reason; waiving an important check also requires an authorized approver.
3. `WEB-INV-03`: A change to a READY specification, acceptance criterion, or DoD increments its revision and invalidates stale approvals.
4. `WEB-INV-04`: AI cannot approve payment, authentication, authorization, privacy, credentials, production data, irreversible migration, public API breakage, or production deployment.
5. `WEB-INV-05`: Tests must not be removed, skipped, weakened, or narrowed to make an implementation pass.
6. `WEB-INV-06`: Capture a pre-change Baseline wherever executable checks exist.
7. `WEB-INV-07`: Repeated failure is bounded by failed-run, same-failure and external-retry limits. Cumulative time is advisory in warn mode and enforced in enforce mode (legacy default). User-requested renewal is additive and auditable, never a history reset or approval bypass.
8. `WEB-INV-08`: Frontend, backend, database, and external integration boundaries are explicit and connected by contracts.
9. `WEB-INV-09`: The client is outside the trust boundary. Client validation, hidden UI, client prices, and client user IDs are never authoritative.
10. `WEB-INV-10`: Completion requires evidence and all required approvals.

## State machine

```text
DRAFT -> READY -> IN_PROGRESS -> VERIFYING -> REVIEW -> DONE
   |        |          |             |          |
   +--------+----------+-------------+----------+-> BLOCKED
```

`STATE.md` owns the current state. Supporting documents own their content, but cannot independently declare workflow completion.

Progress validation permits incomplete states; `validate --gate merge` requires every active task to be DONE with current evidence and approvals. Merge mode cannot use kit mode or select only one task. BLOCKED may resume unchanged READY/IN_PROGRESS work, but returning to DRAFT must use `revise` and a new revision.

### READY gate

A task may enter READY only when:

- scope, exclusions, and acceptance criteria are testable;
- `risk_tier`, `change_domains`, `protected_changes`, and migration class are recorded;
- required plan/ADR documents exist for the tier;
- a valid executed Baseline is recorded against prepared task documents;
- all required design-phase user decisions are scoped and current before implementation (standard receipts or strict signatures);
- no known unresolved ambiguity can lower safety or materially change scope;
- new/revised tasks have complete, source-backed planning analysis and no unresolved
  material questions in CLARIFICATIONS.json (see [question handling](../Runbooks/CLARIFICATIONS.md)).

### DONE gate

A task may enter DONE only when:

- all acceptance criteria have PASS evidence or an authorized exception;
- the required completion profile (Task or Phase with explicit scope configuration; Full for legacy projects) completed successfully;
- source-bound local review is recorded for standard unprotected T1/T2; protected/T3/T4 needs user acceptance of review evidence in standard, or signed independent review in strict;
- approvals match the current source fingerprint;
- known risks and rollback/recovery expectations are documented;
- evidence paths resolve to retained artifacts.

Release is not implied by DONE. Production release is a separate T4 operation.

### Phase integration

With `verification.scopes` configured, a connected feature group is a normal tracked
phase task whose SCOPE.json lists ordinary member tasks. Phase reruns member
acceptance/regression plus integration checks on current source. A current DONE
phase with valid review/approvals may cover its exact historical member evidence
at all-task gates. No phase document owns a second workflow state. Read
[verification scopes](../Runbooks/VERIFICATION_SCOPES.md).

### Archive

Only the active change set belongs in `Docs/Work`. Explicit `archive` revalidates DONE and moves its one STATE plus task records into `Docs/Archive/<TaskId>-r<revision>` without replacing existing history. Reports remain retained. Archive is historical evidence, excluded from future active-task checks, and is not a claim of current release readiness. Complete any intended Release profile first; archived task identifiers cannot be reused.

Before moving the task, archive captures the exact verified source bytes as `SOURCE.zip` with `SOURCE_MANIFEST.json`, checked against the approved Full tree digest. Dirty working-tree changes are preserved rather than represented only by an older commit ID. Potential local credential files are refused; isolate credentials before verification. If the workflow includes a branch/PR merge, complete that integration before archiving. Sequential single-checkout work does not require a merge solely for archiving. Create an active housekeeping task for an archive-only PR subject to the merge gate.

### Baseline with a known failure

Baseline is executable only in DRAFT. It cannot be replaced after READY within that revision. This phase restriction also applies after DONE.

Run Baseline against the original code before fixing it. A required Policy check must PASS. A genuinely executed domain check may fail and its nonzero result can still be retained as `baseline_run` to establish the pre-change condition, provided logs, hashes, source fingerprint, and snapshot remain valid. The Baseline summary and CLI exit remain FAIL; this is not relabelled PASS. NOT_RUN, BLOCKED, missing logs, or stale/tampered evidence cannot satisfy READY. Full remains strict: required checks must PASS or have a current authorized check exception.
