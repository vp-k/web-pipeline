# Durable continuous-development loop

The loop coordinates the active agent. It automatically executes valid transitions and verification commands; implementation and advisory review remain agent actions. It does not launch model APIs, background daemons, production operations, git pushes or independent reviewers. All commands run from an adopted ready project using its local engine:

```console
python -m web_pipeline loop start --plan Docs/Work/loop-plan.json
python -m web_pipeline loop status
python -m web_pipeline loop next
python -m web_pipeline loop complete --token <issued-token> --outcome implemented --decision Docs/Work/WEB-101/decision-001.json
python -m web_pipeline loop retry --task WEB-101 --reason "Required human review was attached and verified"
python -m web_pipeline loop renew --queue --reason "User requested another bounded interval" --extra-minutes 120
python -m web_pipeline loop renew --task WEB-101 --reason "User requested additional failed-run budget" --extra-attempts 5
```

## Start a queue

`Schemas/autopilot-plan.schema.json` defines objective, ordered tasks and explicit dependencies plus optional `max_steps` (default 100), `elapsed_minutes` (default 120), and `completion_gate` (default queue). Select only authorized existing tasks. Unknown dependencies, cycles, duplicate tasks and non-ready projects fail. Dependencies require currently valid DONE, not just a status string.

`Docs/Work/AUTOPILOT.json` owns queue scheduling, not task status. It stores revisions, dependencies, execution cursors, one exclusive action lease, cumulative queue steps and event history. A new queue cannot replace unfinished work. After all previous tasks are still valid DONE, start can preserve the previous checkpoint as `AUTOPILOT-<queue_id>.json` and create a new queue. Task-level iteration limits are never reset.

Plans default to `completion_gate: "queue"` (also when omitted): COMPLETE requires every queued revision's current DONE evidence and approvals, including valid Phase coverage where applicable. The response marks `merge_gate` NOT_APPLICABLE with a reason; it does not claim merge readiness. Set `completion_gate: "merge"` only for an explicitly requested all-active-task merge-readiness workflow. That gate must PASS to return COMPLETE. Failure returns WAITING with the gate's errors, is retained in queue events, and prevents replacement with another queue until resolved. `loop retry` cannot waive this gate; `next` revalidates it. CI still requires its existing `validate --gate merge` independently of queue completion.

Sequential execution uses the current checkout and one action lease. It does not require branch/worktree creation or Git merging. A separate feature branch/PR may still need merging under the repository's existing policy, even with one worker. Parallel work is neither required nor implied by the queue.

## The next/complete cycle

`next` issues one leased action for one worker (execution label `--worker`, default `claude`; `prepare --implementer` uses the same default). The agent performs it, then acknowledges with `complete --token ... --outcome prepared|implemented|reviewed|changes_required|blocked --decision ...`. `complete` returns CONTINUE; it never grants approval. Call `next` again on CONTINUE. Process all runnable authorized work before ending the turn. The active host must keep requesting `next` and performing actions; an exited host must be restarted or resumed explicitly, because the engine cannot wake a stopped Claude Code session.

Planning gates apply inside the cycle: new and revised tasks need [planning analysis and resolved questions](CLARIFICATIONS.md), and PLAN cannot be acknowledged as prepared until that gate passes. New ambiguity during IMPLEMENT/REPAIR requires a blocked acknowledgement before changing bound documents, followed by the normal revise/reconcile flow. `loop retry` never supplies an answer or waives the planning gate.

Completion scope: the loop chooses Task for ordinary scoped work and Phase for a tracked integration group; legacy configurations still use Full. Declare phase members in SCOPE.json and order their tasks before the phase in the queue. Phase evidence can cover the members' historical source only after rerunning their checks on current combined source. All profiles retain review and iteration limits. See [verification scopes](VERIFICATION_SCOPES.md).

Workspace state is checked before every action: unmerged index entries or unfinished merge, rebase, cherry-pick, revert or sequencer state block the entire checkout before another action is scheduled or acknowledged as successful. Checks resolve the worktree-specific Git directory. Retain the failed command, exit code and conflict details; resolve and finish the operation, or explicitly abort after inspecting the changes. Do not automatically discard work. A failed external Git command with no retained operation marker must still stop its invoking agent/script; the loop does not execute or intercept it.

## Review and approval inside the loop

Shipped adoption uses `approval_policy: standard`. Ordinary unprotected T0–T2 needs no human name or trust file. T1/T2 reviewed completion records `LOCAL_REVIEW-<completion-summary-hash>.json` with choice/rationale/alternatives/risks and source/evidence binding; the loop writes it on the `reviewed` outcome, and manual work uses `review --task ... --decision ...` after entering REVIEW. These are local self-review records, not independent review or human approvals. Protected/T3/T4, exception and Release decisions in standard use explicit user receipts through `approval-request` and `approve`; see [APPROVALS.md](APPROVALS.md). AI review cannot substitute for that user decision. Supply `--trust` only for strict or existing signed records. An existing config without the policy field remains strict; upgrades do not change it.

## Outcomes and exit codes

`next` returns ACTION_REQUIRED, BUSY, WAITING, PAUSED_LIMIT or COMPLETE. Blocked tasks can be skipped only when the next task's dependencies and gates permit it. Retry after new external evidence clears scheduling wait only, not an engine gate or budget. Task-only budget exhaustion also returns PAUSED_LIMIT when all remaining waits are budget-related.

WAITING, BUSY, PAUSED_LIMIT and FAIL return a nonzero CLI exit from loop actions. Other handled commands may return zero without completing work; consume the JSON status and continue on CONTINUE. `loop status` is a read-only query: it shows queue and task accounting and always exits zero, whatever the queue status.

## Choice and evidence trail

- START records the objective, task order and dependencies.
- SELECT records why a task/action was selected, waiting or later alternatives, actor token, revision, prepared-document fingerprint, source tree digest, STATE hash and completion run reference.
- EXECUTED records actual transitions/run IDs/results. WAIT/WAITING record gate and dependency reasons.
- LEASE_END records the completed/recovered lease token and charged active seconds. Queue RENEW events mirror additive grants; task grants live in `STATE.iteration.renewals` with usage/migration/settlement evidence.
- DECISION requires a schema-valid choice, rationale, nonempty alternatives and risks array, plus before/after identities. AI review decisions are advisory, bound to the validated completion summary; they cannot satisfy a user receipt or a human signature.
- RECOVER, RETRY and RECONCILE record why execution or scope resumed. History is preserved through the CLI but is not cryptographically trusted against a filesystem writer. Retain checkpoints with original reports in protected storage for independent audit.

Example decision:

```json
{
  "choice": "Validate the submitted resource owner on the server",
  "rationale": "Client-side visibility does not enforce access control",
  "alternatives": ["Client-only hiding rejected because direct API requests bypass it"],
  "risks": ["Authorization policy still needs its protected design approval"]
}
```

Important architecture/security choices still need the project's ADR and the protected design approval: a scoped user receipt in standard policy, a signed record in strict. Choice logs do not replace them. The engine validates structure and evidence bindings, not the truth or quality of an agent's reasoning.

## Rework and scope changes

Failed Fast/Task/Phase/Full requests REPAIR; successful verification requests advisory REVIEW. Changes-required transitions REVIEW back to IN_PROGRESS and clears previous completion/Release pointers. Rework must obtain new verification and, where the tier or protected changes require it, new user receipts (standard) or signatures (strict); a T1/T2 unprotected task needs a fresh local review record.

After a user-authorized scope change, use `revise` then `loop reconcile --task ... --reason ...`; the new DRAFT revision is pinned without resetting budgets. If another task changes shared source, old REVIEW/DONE evidence can become stale. The loop fails closed; inspect and reconcile/reverify rather than manufacturing approval or automatically rewriting requirements. Task granularity and dependency order must respect this repository-wide source binding.

## Leases and recovery

A lease is persisted before execution. A second `next` returns BUSY, and stale or duplicate complete tokens are rejected. There is no automatic lease expiration or blind action replay. After inspecting actual effects and verifying no other worker/process remains, run `loop recover --token ... --reason ...`, then retry when safe. Crash recovery preserves steps, task attempts and code; exactly-once side effects are not promised. The cooperative lease does not police arbitrary filesystem writers or unrelated engine commands.

An abandoned lease is charged from claim to explicit recovery. Without a heartbeat there is no evidence to separate offline time from active work while it remained claimed; recover is conservative, not an automatic idle subtraction. For a planned pause, finish the action or complete it as blocked before leaving the session.

Verification reserves an unresolved/non-PASS attempt before executing. A crash leaves `pending_run`; later runs refuse to start until it is inspected. Inspect and release a process lock only after proving no process owns it (`locks --clear-stale` removes locks whose owner is provably gone); renew never steals locks.

Checks must finish their descendants. Windows commands start inside a Job Object before their first instruction; timeout and exit cleanup terminate the job tree. A command abandoning a running descendant fails even if the parent exits zero. POSIX uses a dedicated process group and kills it after parent exit or timeout. This is lifetime containment for cooperative verification commands, not a sandbox for malicious commands that deliberately escape POSIX sessions.

## Budgets and renew

`attempts` counts every Fast/Task/Phase/Full execution; only `failed_attempts` spends the configured `total_attempts` budget (default 5). Successful verification does not spend failed-run budget. Queue steps count issued machine/agent actions, including interrupted actions. Queue time sums lease intervals; task time sums verification summary `started_utc` to `completed_utc`. Original started timestamps are retained for provenance, not used as expiration clocks. Time between leases, including approval waiting and ordinary session shutdown, does not spend queue time.

New adoption uses `iteration_limits.time_budget_mode: "warn"`: cumulative time is advisory, reported in warnings without stopping execution or truncating a check. New queues freeze that default in their plan unless explicitly overridden. Missing mode in existing configs/checkpoints retains `enforce`; an upgrade never silently changes their limits. Per-command timeouts and failed-attempt/same-failure/external-retry/step guards remain enforced.

In enforce mode, a conclusive budget-only interruption stays BLOCKED but refunds its reserved failed attempt and does not spend an external retry. Mixed real failures and unknown results still spend failed-run budget. Budget-only interruption preserves the preceding same-failure guard rather than replacing it with a timeout fingerprint. Genuine execution blockers and command-specific timeouts still count normally. Queue limits are checked between actions; in-flight verification has its own task budget/command timeouts. An agent must return/complete its lease; the CLI cannot kill a host model.

Same-failure identity includes normalized retained error output. Different failures sharing exit code 1 do not accumulate as the same defect; timestamps, durations, PIDs and ordinary progress output do not disguise an unchanged error. Cumulative failed attempts, external retries, existing stop counters and renewal rules are unaffected by engine updates; installing an update does not erase historical usage or authorize retrying an already exhausted guard.

Renew procedure:

1. Inspect `loop status`, task STATE, diffs, original reports and running processes. Complete or explicitly recover an open lease first. Do not renew under a live worker. A task can be renewed without an existing queue; queue renewal needs one.
2. Use the user's explicit request to resume with a bounded additional budget; if already given, do not ask again. Time warnings in warn mode need no renewal. Record that reason via `loop renew --queue` or `loop renew --task ID`. They are exclusive targets; if both limits are exhausted, renew each separately. No trust file or human name is needed. Each grant accepts 0–1440 extra minutes and 0–1000 extra attempts, with at least one positive; queue extra-attempts means additional steps.
3. The original config/plan is unchanged. Effective budget is original limit plus the sum of `renewals`; usage, initial timestamps and old grants are not reset. Inspect `remaining_limit`. Renew does not clear `same_failure`, `external_retries`, cached external waits, approvals, exceptions, scope or failed verification.
4. Use `loop next` again. For an old cached wait whose cause is actually resolved, use `loop retry --task ... --reason ...` first. Never renew automatically in an unlimited loop; a generic earlier keep-going request is not repeated renewal authorization. Revising does not create fresh budget.

Task renew settles its budget using the retained summary, or conservatively charges elapsed time and keeps a failed attempt if no summary survived. It does not restore a completion pointer, replay the command, or change same-failure/external counters.

## Connected implementation order

For coupled provider/consumer work, the queue supports explicit `implementation_groups`. Follow [IMPLEMENTATION_GROUPS.md](IMPLEMENTATION_GROUPS.md): prepare contract/scope and all members/Phase; capture every member Baseline and entry gate; implement in the declared backend/frontend order; execute unchanged member Fast/Task/review gates; then execute the Phase gates. Do not substitute an internal completion dependency for implementation order or remove integration tests.

## Older adopted projects

Plugin reinstall updates the plugin, not adopted engines; upgrade the project engine explicitly through [UPDATES.md](UPDATES.md), preserving project-specific config, commands, source specs, all `Docs/Work` and original Reports. Do not replace the project with kit defaults. Engine/source changes invalidate old completion/release evidence; renew is not migration approval or permission to reuse stale reports. Follow ordinary revision/reverification and protected-change gates where applicable.

Old records without `budget_version` remain readable. `loop renew` explicitly converts each target: queues reconstruct SELECT-to-outcome lease intervals from their complete history; tasks reconstruct failed runs and active seconds from retained verification summaries across revisions. The renewal retains the original iteration block or queue hash and evidence hashes. Missing task reports cause a conservative conversion (all old attempts treated as unresolved failures, old elapsed time frozen as usage), not an invented zero. Malformed or incomplete queue action history blocks conversion until the original checkpoint is restored. Unmigrated old records cannot silently start a new budget; renew the task and queue as required. Current scope/revision/dependency and approval gates still apply.

## Diagnose before stopping

Follow [CONTINUATION.md](CONTINUATION.md). ACTION_REQUIRED is an agent action, not user permission. WAITING/FAIL first require diagnosis and authorized recovery. Only unresolved external decisions/resources, hard limits or the user's stop require yielding. A routine repair or Git conflict resolution within the request does not require another permission question.
