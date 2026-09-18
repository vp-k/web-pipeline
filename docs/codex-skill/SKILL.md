---
name: web-development-pipeline
description: Adopt, configure, audit or operate the standalone Web Development Pipeline for web repositories with risk tiers, tracked tasks, verification evidence and human approval gates. Use for explicit web pipeline requests or tracked work in a repository already using this pipeline; not for ordinary unrelated web edits or the game pipeline.
---

# Web Development Pipeline

Use this skill as the operating interface to the bundled, standalone Python engine. It is not a game-pipeline profile. Installation adds reusable capabilities, not project readiness or permission to deploy.

## Select the requested operation

Resolve this skill's directory from the loaded SKILL.md path; never hardcode the original developer checkout or a plugin cache location. The examples use `<skill>` for that resolved directory and `<project>` for the user's explicit target. Paths with spaces must be quoted.

- **Adopt/configure:** read [references/adoption.md](references/adoption.md). Inspect the target before any write. Use the bundled bootstrap only for new adoption, never to replace an existing engine or user instructions.
- **Inspect/update/restore:** read [references/adoption.md](references/adoption.md) and bundled `Docs/Runbooks/UPDATES.md`. Use `inspect`, adoption `--preview`, or default upgrade preview without writes. Only an explicit update request authorizes `upgrade --apply`; preserve project-owned files, compare dependency/runbook changes, and retain backups. Never fabricate a legacy baseline or silently upgrade during ordinary task work.
- **Work/verify/resume:** read the target's AGENTS.md, pipeline.config.yaml and the selected Docs/Work task, then [references/operations.md](references/operations.md). Use the project-local engine and rules, not the plugin's possibly different engine version.
- **Continuous development / keep iterating / resume a queue:** additionally read [references/continuous.md](references/continuous.md). Use the durable loop and keep acting on nonterminal results until the authorized queue is complete or a real stop condition is reached. Intermediate reports, a passing test, and an advisory review are not stop conditions.
- **Review/status/audit:** read the same project instructions and relevant governance documents. Inspect state, configuration and retained evidence; run read-only validation where authorized. A review request does not authorize adoption, fixes, state transitions, new verification runs, archive or deployment.

Read the target's mandatory domain runbooks before domain actions. During adoption, their maintained copies are under `assets/pipeline/Docs/`; after adoption the project's copies govern. Do not load every runbook for an unrelated domain.

## Required order when starting project implementation

For new adoption followed by implementation, follow the stage exit criteria in
[references/adoption.md](references/adoption.md#first-feature-before-expansion):
**map the repository and stacks -> connect real checks -> validate one complete
feature -> expand to the remaining authorized features**. Do not start bulk feature
implementation after installation or configuration alone. Keep the first feature
tracked through its required member/Phase verification, review and approvals;
later features wait for that evidence. If the user requested the whole project,
continue after this gate without asking permission again. For an existing project,
inspect and reuse applicable retained evidence instead of restarting adoption or
inventing a new pilot on every task. These are agent operating instructions;
engine enforcement uses the existing task/Phase gates and explicit queue dependencies.

For frontend/backend/API work or boundary configuration, also read the maintained
`Docs/Runbooks/BOUNDARIES.md`. With engine 2.6, map actual browser/server/shared
components, permitted imports and contract provider/consumer checks. Do not force
separate repositories or invent a backend for a static site. A missing boundary
model is NOT_CONFIGURED, not evidence of isolation. Configure new web adoption;
upgrade existing project engines/configuration only with explicit scope. Use a
stack-appropriate real graph adapter and integrated-flow checks, not placeholder
commands, filename-only guesses or mocks as the sole connected-feature evidence.

## Entry points

Requires a shell/filesystem, Python 3.11+, Git, and dependencies in `assets/pipeline/requirements.txt`. No MCP server, API key or background hook is required. If unavailable, report the missing dependency; do not claim a run occurred. Do not install dependencies globally as an implicit side effect.

```console
python "<skill>/scripts/pipeline.py" doctor
python "<skill>/scripts/pipeline.py" inspect --target "<project>"
python "<skill>/scripts/pipeline.py" adopt --target "<project>" --preview
python "<skill>/scripts/pipeline.py" adopt --target "<project>"
python "<skill>/scripts/pipeline.py" project --root "<project>" validate
```

The wrapper verifies the bundled asset inventory before adoption or maintenance. Project commands require an adopted local engine; there is no silent fallback to the bundled engine. Use an appropriate existing project interpreter or a scoped virtual environment when dependencies differ. Engine 2.7 test commands may declare structured results: read `Docs/Runbooks/TEST_RESULTS.md`, use real reporters, and distinguish validated test cases from legacy exit-code-only checks. The runnable `examples/web` demonstrates real browser/API/SQLite evidence, not universal framework or production coverage.

## Verification scope (engine 2.8+)

For new adoption map real component paths, dependencies and separate suite commands
using the bundled `Docs/Runbooks/VERIFICATION_SCOPES.md`. Existing projects need an
explicit engine/configuration update; absence of scopes retains legacy Full.
For work, inspect `verification-plan --task <id>`: use Task at ordinary completion,
Phase for a tracked connected feature group, and project-wide Full/Release when
required. Unknown impact, broad inputs and protected/T3/T4 work expand automatically.
Do not run the entire project after every small edit or shrink a suite to hide failure.
Phase membership lives in fingerprint-bound SCOPE.json; only its STATE owns status.
Preserve member evidence/reviews and use the existing gates for phase coverage.

## Preserve the control boundaries

Infrastructure provisioning, hosting configuration, deployment and production
operations are user-owned. Unless explicitly requested, exclude them from planning,
task queues and development completion criteria. Finish application implementation,
required local/test verification, review and evidence without requiring hosting
access, deployment credentials or Release readiness. Record application runtime
requirements needed for handoff. If the user explicitly requests infrastructure
or deployment work, apply the project's existing classification and approval rules.

For task planning with engine 2.10+, read the project's `Docs/Runbooks/CLARIFICATIONS.md`.
Resolve material uncertainty primarily while drafting initial requirements. Inspect
existing evidence first; ask grouped concrete questions about scope, behavior,
exceptions, data, constraints and acceptance when evidence does not determine them.
Wait for actual answers before dependent implementation. Fill CLARIFICATIONS.json
with analysis, source excerpts and answers mapped to acceptance; run
`clarification-report --task <id>` before prepare. CLEAR is not readiness or approval.
New/revised tasks enforce the record; legacy missing coverage is NOT_CONFIGURED.
On late uncertainty, acknowledge any active implementation lease as blocked before
editing bound records, then use revise/reconcile and ask only the newly unresolved
questions. Silence and agent proposals are never user answers. This does not add
ordinary approval prompts or replace protected gates.

For coupled backend/frontend implementation with engine 2.9+, read the project
`Docs/Runbooks/IMPLEMENTATION_GROUPS.md`. Explicit queue groups enforce all member
Baselines/entry gates, declared implementation order, unchanged member checks/review,
and then Phase checks/review. Do not drop integration tests or confuse implementation
order with `depends_on`, which still requires completed evidence and approvals.
Engine 2.9.1 resolves every member's external prerequisites before group Baselines,
reserves setup/initial implementation against unrelated queue work, and rechecks
all peer entry conditions before each IMPLEMENT/REPAIR action. Resolve reported
peer blockers or scope drift before continuing; preserve original Baseline evidence.

- State is owned only by the task's STATE.md and engine transitions. Never hand-edit status, run pointers or iteration counters to pass a gate.
- `validate` is a progress diagnostic. Only `validate --gate merge` checks every active task for merge readiness; kit validation never proves project readiness.
- Sequential work uses the current checkout; do not introduce branches/worktrees or merges solely for the pipeline. Queue completion defaults to requested-task verification. Use `completion_gate: "merge"` only for explicitly requested merge readiness; failure is WAITING, never COMPLETE. Stop on failed required gates/Git commands and unresolved integration before starting unrelated work. Preserve errors and changes; never replace the queue or discard work to bypass failure. Existing PR/CI requirements still apply.
- Classify through T0–T4, change_domains and protected_changes. Prepare documents before capturing Baseline in DRAFT, then enter READY only with the required approvals. Do not recapture a post-change Baseline as pre-change evidence.
- READY scope/AC/DoD changes require `revise` and renewed evidence/approvals. Usage and renewal history remain cumulative. Time warnings in `time_budget_mode: warn` do not stop work or require renewal; existing missing-mode configs/checkpoints retain enforce. On enforced limits, report them; a new user request to resume may authorize one bounded `loop renew --queue` or `--task ...` grant. Read continuous guidance, record the request/reason and added budget, then resume through existing gates. Never self-renew repeatedly under an earlier generic keep-going instruction.
- Do not weaken tests, commands or requirements to obtain PASS. PASS, FAIL, NOT_RUN, BLOCKED, NOT_APPLICABLE and INCONCLUSIVE retain their distinct meanings. Authorized N/A is not executed PASS.
- New adoption uses `approval_policy: standard`: unprotected T0–T2 work needs no human name or external trust setup. T1/T2 still needs actual review and a source-bound decision record; the loop records it on `reviewed`, or use `review --task ... --decision ...`. Self-review is not independent review or human approval. `prepare` and `loop next` default to the execution label `codex`.
- Continue ordinary implementation, repair, verification and local review within the user's requested scope across workflow stages and queued tasks; a stage transition alone is not a reason to ask permission again. Request separate approval only where the project's policy requires it. Inspect actual prior consent first: AWAITING_USER with CHECK_EXISTING_CONSENT requires transcription/evidence repair before a new question. Saved old requests do not override current STATE. approval-request returns NO_APPROVAL_REQUIRED or SATISFIED when no new user decision is needed; continue without prompting. For a required protected decision, group the currently reviewable decisions/roles into one concise question for that approval phase. Cite the gate and explain the missing or changed scope/evidence binding. A protected design approval does not approve the resulting implementation, a check exception, risk acceptance, release readiness or production execution; preserve those specific approval boundaries without applying them to ordinary workflow transitions.
- With project engine 2.5+, standard protected/T3/T4, exception and Release gates accept a source-bound record of explicit user consent: read [references/approvals.md](references/approvals.md). Do not ask for identity/trust in standard. Strict (including missing policy) retains signatures. Never invent user consent, human identities, signing keys or independent review; do not silently change project policy or substitute the bundled engine for an older project engine.
- Release is readiness verification only. Plugin installation, task completion and verification never authorize production deployment, production data edits, credential rotation or destructive migrations.

Report the task/revision, actual status, executed checks, evidence paths, failures and missing approvals. Distinguish engine checks from semantic test coverage and external CI/credential enforcement. Never label the whole feature complete just because the plugin installed or a command exited zero.

Record meaningful implementation/repair/review choices through loop completion: choice, rationale, considered alternatives and residual risks. Automatic queue selection reasons and source/state identities are retained in the checkpoint history. These AI records do not replace required ADRs or explicit user decisions.

## Product focus and continuation

Follow project `Docs/Runbooks/PRODUCT_FIRST.md` and `CONTINUATION.md` when available. Use actual domains, existing documents/checks and one real requested first feature. A small connected feature may be one task; implementation groups are for already split mutually dependent members. Do not build pipeline infrastructure as a product prerequisite. Diagnose WAITING/FAIL and perform authorized recovery before yielding; use an available reviewer or a real separate self-review for ordinary standard work. Optional archival may use an explicit scoped standing request, with all validation intact.
