# Web pipeline operating rules

This project is governed by the web pipeline engine in `web_pipeline/`. `CLAUDE.md` imports this file; project-specific rules stay in `CLAUDE.md`. Run every command from the project root as `python -m web_pipeline <command>`.

Start every session with `python -m web_pipeline status`. It is read-only and reports readiness, open tasks, held locks, the queue and the next step.

## Workflow mode

`workflow` in `pipeline.config.yaml` selects how ordinary changes are tracked. A missing value means `tracked`.

- `lean`: follow [LEAN.md](Docs/Runbooks/LEAN.md). Build one feature with its tests, run `python -m web_pipeline check` before each commit, get one fresh-context review and put the check table in the commit message. For a whole project, keep the features in build order with `feature add`, `feature next` and `feature done`. Do not create `Docs/Work` tasks for ordinary work. Lean starts with the checks that are enabled and reports the rest as `missing_checks`.
- `tracked`: every change is a task under `Docs/Work` and follows the Flow below.
- In both modes, payment, deployment, release, production operations and destructive migrations use a tracked task.
- Rules 4 to 9 below apply in both modes. Rules 1 to 3, rule 10 and the Flow apply to tracked tasks.

## Non-negotiable rules

1. Read `pipeline.config.yaml` and the task folder `Docs/Work/<TaskId>/` before changing product code.
2. `Docs/Work/<TaskId>/STATE.md` is the only workflow-state owner. Change it only through engine commands (`new`, `prepare`, `transition`, `revise`, `archive`); never hand-edit it and never represent a task as READY, approved, reviewed or DONE anywhere else. An archived task under `Docs/Archive/` is historical evidence, not current readiness.
3. Run Baseline before implementation whenever an executable baseline exists. `NOT_RUN`, `BLOCKED` and `NOT_APPLICABLE` are recorded honestly; none of them means PASS.
4. Never delete, skip, weaken or narrow a test to obtain a passing result.
5. Never lower a risk tier selected by policy. When uncertain, use the higher tier.
6. Never fabricate owners, approvals, dates, source revisions, commands, screenshots, logs or test results. Never hand-edit anything under `Reports/Pipeline/`.
7. You may draft an ADR, risk acceptance, review or release record. You may not approve your own protected decision or act as the independent reviewer of your own implementation. In standard policy you transcribe the user's explicit, scoped approval through `approval-request` then `approve`; that is a local user-decision receipt, not AI approval. Never ask for identity or trust files for a standard receipt. Strict policy keeps signed human gates. See `Docs/Runbooks/APPROVALS.md`.
8. Do not deploy to production, mutate production data, run a production migration, rotate credentials or accept risk unless the user explicitly requests it and the human approval gate is satisfied.
9. Treat browser input and client state as untrusted. UI validation and hidden controls are not authorization controls.
10. Completion requires evidence and every required approval.

## Flow

`Scope + planning questions -> classify -> new -> prepare -> Baseline -> READY -> implement -> Fast -> Task verification -> REVIEW -> DONE -> report`

- Within the user's requested scope, continue implementation, repair, verification and local review without asking permission at each step. A stage transition alone does not need renewed consent. In standard policy, unprotected T0-T2 work has no user-approval gate.
- Before asking about protected work, inspect existing consent and recorded approvals. Do not repeat a question for a still-valid phase and scope. Group everything a phase requires into one concise question, after preparing the concrete decision and evidence. A design approval does not approve implementation results, exceptions, release readiness or production execution.
- Resolve material questions during planning. Inspect existing evidence first; ask concrete questions when uncertainty changes scope, behavior, data, architecture or acceptance, and wait for the actual answer. Silence or your own proposal is never an answer. Record sources and resolutions in `CLARIFICATIONS.json` (`Docs/Runbooks/CLARIFICATIONS.md`).
- With `verification.scopes`, ordinary tasks complete with Task and connected feature groups with a tracked Phase task (`Docs/Runbooks/VERIFICATION_SCOPES.md`). Unknown impact, broad inputs and T4 work expand to project-wide checks. Protected/T3 work adds its own domain and protected checks without running every other suite. Project-wide Full is not required after every small edit.
- Local self-review (`review`) covers standard, unprotected T1/T2 work only. Use a fresh-context reviewer when available; otherwise perform a separate local review and identify it as self-review; write the decision JSON inside `Docs/Work/<TaskId>/`.
- Release is a separate T4 gate and is never implied by implementation completion.
- `new` pins `base_ref` to the current commit unless `--base-ref` names another; `prepare --base-ref` sets or repairs it while the task is a DRAFT.
- DONE is history. The DONE transition records a completion seal of the approval rules, cited planning documents and boundary contracts the task was completed against; later work in the shared tree does not make it stale. The merge gate stays strict: integrated work still needs a current Phase run.
- `revise` carries the task's `CLARIFICATIONS.json` and its ADRs into the new revision and lists them as `carried` in `REVISION_HISTORY`. Update what changed; answers stay.
- `archive` moves a DONE task to `Docs/Archive/` with `EVIDENCE.zip`: the run summaries, the hash-checked artifacts and the configuration they ran under.
- Infrastructure, hosting, deployment and production operations belong to the user. Keep them out of plans, queues and completion criteria unless explicitly requested; record runtime requirements needed for handoff.
- Sequential work uses the existing checkout. Do not create a branch or worktree, or require a merge, only because the pipeline is running. A merge-readiness check performs no Git merge.
- A failed required gate or Git command blocks dependent progress, not authorized repair: keep the error, diagnose and resolve it in the same request before unrelated work. Never hide a nonzero exit, discard changes or start a replacement queue to get around a failure.
- If a command reports a held lock, run `python -m web_pipeline locks`. A lock whose process is gone is reclaimed automatically; never delete a lock whose process is alive.

Read [CONTINUATION.md](Docs/Runbooks/CONTINUATION.md) before treating a diagnostic as a user stop. In `time_budget_mode: warn`, elapsed-time warnings do not require renewal. Hard retry/step limits remain.

## Work rhythm

Implement one feature, check it with the relevant checks, then move to the next.

- While implementing, run Fast for the changed components and fix what fails.
- When the feature works, run its completion profile once, review it and close it. Project-wide verification belongs to the integrated change (Phase/Full).
- Do not rerun a verification that failed or was interrupted for the same cause until that cause is fixed. If it cannot be fixed, record the blocker in one line and continue unblocked feature work.
- Do not write procedural notes the engine does not require (resume notes, execution notes, cleanup logs). STATE and evidence carry the state.
- Report delivered features and actual check results, not how many procedures ran.

## Product work first

Follow [PRODUCT_FIRST.md](Docs/Runbooks/PRODUCT_FIRST.md): reuse existing documents, checks and layout; configure actual domains; implement one real requested feature as soon as its entry gates pass. Do not invent a pipeline demonstration feature or split a small connected feature into multiple tasks just because it crosses layers.

## Planning documents

Use `PLAN.md` for T2 work and a living `EXEC_PLAN.md` for T3/T4 or multi-milestone T2 work. A plan states: objective and exclusions; affected domains and trust boundaries; contract and data-shape changes; migration and compatibility strategy; milestones with observable outcomes; verification mapped to acceptance criteria; rollback or recovery for T3/T4; decisions and approvals still required. When reality diverges, add a dated note instead of rewriting history. Plans never override `STATE.md`; READY requirements are in `Docs/Governance/00_OPERATING_MODEL.md`.

## Required reading by domain

- Lean: `Docs/Runbooks/LEAN.md`, then only the domain runbooks below that the feature touches.
- Tracked tasks: `Docs/Governance/00_OPERATING_MODEL.md`, `RISK_CLASSIFICATION.md`, `VERIFICATION_POLICY.md`.
- Protected or T3/T4 tracked tasks: `PROTECTED_CHANGES.md`, `APPROVAL_GATES.md`, `ROLE_MODEL.md`.
- Frontend: `Docs/Runbooks/FRONTEND.md`. Backend: `Docs/Runbooks/BACKEND.md`. Database: `Docs/Runbooks/DATABASE.md`.
- Frontend/backend/API boundaries or adoption: `Docs/Runbooks/BOUNDARIES.md`. API or external integration: `Docs/Runbooks/API.md`.
- Authentication, authorization, security or privacy: `Docs/Runbooks/SECURITY.md`.
- Release or deployment: `Docs/Runbooks/RELEASE.md`. Continuous queue: `Docs/Runbooks/CONTINUOUS.md`.
- Pipeline setup or CI: `Docs/Runbooks/CONFIGURATION.md`, `Docs/Governance/ENFORCEMENT.md`.

## Evidence

Generated evidence lives under `Reports/Pipeline/<RunId>/`. In a tracked task, each criterion in `ACCEPTANCE.json` lists the configured check IDs that prove it. REVIEW, DONE and Release readiness need those checks to PASS in the completion or Release run.
