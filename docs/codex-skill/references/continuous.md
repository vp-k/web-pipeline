# Continuous development in the active session

Use this mode when the user asks to keep developing, iterate until complete, or resume an existing continuous queue. Do not turn an isolated review/status request into implementation. The project engine must support `loop`; an older installed engine requires an explicitly scoped upgrade, not a silent bundled-engine fallback.

## Create or resume the authorized queue

Read the project rules and current tasks first. Create the scoped DRAFT tasks/documents where authorized; do not invent new features. For an existing `Docs/Work/AUTOPILOT.json`, inspect `loop status` and resume instead of starting over. STATE.md remains the only task status authority.

For a newly adopted project's first implementation, follow
[adoption.md](adoption.md#first-feature-before-expansion) before queuing the broader
backlog. Queue the first complete feature and its prerequisites first, or make
every later feature explicitly depend on its Phase/task completion. After that
gate passes, continue the remaining authorized scope without another permission
question. Resume from retained evidence instead of repeating a completed adoption.

Create a plan file under Docs/Work with the user's actual objective and task IDs, explicit dependencies, and bounded queue budget. Example structure (replace fixture task IDs with actual tasks):

```json
{
  "objective": "Complete the agreed profile feature and its tests",
  "max_steps": 100,
  "elapsed_minutes": 120,
  "tasks": [
    {"task_id": "WEB-101", "depends_on": []},
    {"task_id": "WEB-102", "depends_on": ["WEB-101"]}
  ]
}
```

An empty depends_on explicitly means the task can be scheduled independently, not that it is immune to shared-code changes. Dependencies require currently validated DONE, including human approvals where required. Do not drop a dependency just to advance.

Engine 2.9 supports explicit `implementation_groups` for a prepared Phase and its
DRAFT members when connected tests require both implementations. Read the project
`Docs/Runbooks/IMPLEMENTATION_GROUPS.md` and use its concrete plan: define contracts
and scope, prepare every member and Phase, capture all member Baselines and entry
gates, implement backend then frontend in the group's `order`, run every unchanged
member Fast/Task/review gate, then verify/review the Phase. Internal `depends_on`
completion edges conflict with this barrier and are rejected; implementation order
belongs in the group. Do not skip Task integration tests or omit the Phase.

```console
python "<skill>/scripts/pipeline.py" project --root "<project>" loop start --plan "<project>/Docs/Work/loop-plan.json"
python "<skill>/scripts/pipeline.py" project --root "<project>" loop next
```

Standard needs no human identity or trust: ordinary T0–T2 uses local review; protected/T3/T4 uses explicit user approval receipts in engine 2.5+. Read [approvals.md](approvals.md) when a user decision is needed. The worker/implementer default `codex` is an execution label, not a human. Supply --trust only for strict or existing signed records. Never create a human trust store or supply a test key for a real task. Read `Docs/Runbooks/CONTINUOUS.md` in the project for engine behavior and recovery details.

## Keep going on nonterminal results

1. Call `loop next`. It advances legitimate transitions and actual Baseline/Fast and configured Task/Phase/Full completion verification until agent work is needed or no further authorized work is runnable.
2. On ACTION_REQUIRED, inspect the task, current evidence and the action:
   - PLAN: fill the documents, contracts, acceptance mapping and tier-required ADR drafts; prepare the DRAFT through the CLI. Do not change product code before Baseline or invent accepted ADRs/approvals.
   - IMPLEMENT: implement only the prepared scope.
   - REPAIR: inspect the latest failing report or review decision in loop status; make a hypothesis-driven correction, preserving tests and scope. Do not blindly rerun the same command.
   - REVIEW: inspect code, acceptance and actual completion evidence without editing source. Record reviewed or changes_required. In standard unprotected T1/T2 work, reviewed persists a source-bound local review that satisfies the local review gate. It is self-review/advisory evidence, never independent human approval; protected/T3/T4 still needs a separate user receipt in standard or signatures in strict. Use another agent only when delegation is authorized and available.
3. Write a decision JSON inside the task's Docs/Work directory. Required fields are choice, rationale, alternatives (at least one concrete considered option), and risks. When no meaningful alternative exists, explicitly say why, rather than inventing one. Never put credentials or personal data in decisions.
4. Acknowledge the token with the valid action outcome:

```console
python "<skill>/scripts/pipeline.py" project --root "<project>" loop complete --token <token> --outcome implemented --decision "<project>/Docs/Work/WEB-101/decision-001.json"
```

   Outcomes: PLAN → prepared; IMPLEMENT/REPAIR → implemented; REVIEW → reviewed or changes_required. Use blocked plus an honest reason if the action cannot proceed. The engine validates prerequisites; the outcome does not set task PASS or DONE.
5. On CONTINUE, immediately call `loop next` and repeat **without ending the turn or asking whether to continue**. Send brief progress updates while continuing. Failure repair, review rework and next-task selection are part of the same request.

## Real stop conditions and recovery

- COMPLETE: every queued revision has current DONE evidence and required approvals. Plans default to `completion_gate: "queue"`; merge_gate is NOT_APPLICABLE, not PASS. Set `completion_gate: "merge"` only when merge readiness was explicitly requested; its failure returns WAITING and prevents replacing the queue. Queue completion never deploys or merges automatically.
- Unfinished Git integration: stop work across this checkout. `next` reports WAITING and refuses new actions; a pending action cannot be acknowledged as successful. Resolve and finish the operation or explicitly abort after inspection. A failed Git command must stop its caller even if Git left no operation marker. Preserve errors and changes; do not skip the failure or create another queue.
- WAITING: no queued task can safely proceed. Report each missing approval, dependency, stale scope/evidence or external blocker and the next required decision. Independent eligible tasks are already considered before this result. Do not keep calling next on unchanged WAITING.
- PAUSED_LIMIT: report both queue and task limits. A new user request to resume can authorize one bounded `loop renew` grant with that request's reason; no human name/trust is needed for budget renewal. Otherwise stop and ask for the needed budget. Do not self-renew repeatedly, edit initial limits, delete the queue, manufacture new tasks, or reset usage.
- BUSY: an unfinished action owns the queue. Do not run a second worker. After a crash/session change, inspect task state, diffs, running processes and evidence; explicitly recover the exact token with inspection notes, then retry only when safe. Recovery does not undo or blindly replay work, and it never resets budgets.
- Explicit user stop, revoked authority, or unavailable host execution also stops the loop.

If an approval or external condition arrives, verify it and use `loop retry --task ... --reason ...` before next. If the user changes scope, use normal `revise`, then `loop reconcile` with the authorized reason; do not silently change queue revisions. Stale DONE or review evidence caused by shared-source changes still requires explicit safe reconciliation/reverification, not reuse of old approval.

The checkpoint is resumable across sessions, but this package is not a daemon and does not launch another model session after the host exits. Use a new authorized session to resume. Do not claim unattended 24/7 operation.

## Budget renewal (project engine 2.4+)

Inspect `loop status`: queue active usage and each task's iteration budget are
separate. After a user asks to resume, renew only the exhausted budget(s), once per
authorized additional interval. If no amount was specified, one default-size grant
(120 minutes, or 5 failed attempts for a task / 100 steps for a queue) is a bounded
interpretation; state the amount to the user. Do not add attempts for a time-only
limit. An earlier generic "keep going" is not unlimited renewal authorization.

```console
python "<skill>/scripts/pipeline.py" project --root "<project>" loop renew --queue --reason "User requested resuming the existing queue" --extra-minutes 120
python "<skill>/scripts/pipeline.py" project --root "<project>" loop renew --task WEB-101 --reason "User requested another bounded attempt interval" --extra-attempts 5
python "<skill>/scripts/pipeline.py" project --root "<project>" loop next
```

Renew accepts exactly one target, positive additional minutes and/or attempts, and
a substantive reason; never --trust. Queue extra-attempts means scheduling steps.
Inspect remaining_limit in the response. Approval, same-failure, external-retry and
stale-evidence gates remain effective. Old 2.3 cached waiting messages may need
`loop retry` after their actual cause is resolved; retry does not reset counters.

An open lease must be completed or explicitly recovered before renew. If the host
exited holding a lease, recover conservatively accounts its entire interval; do
not invent an idle-time subtraction. For a normal pause, complete the action as
blocked before leaving the session. Time with no lease is free of queue time cost.
Task time sums Fast/Full run intervals; successful checks no longer exhaust the
failed-run budget. Pending verification is inspected before renew settles its
reservation; ensure no process is still running. No unknown run becomes PASS.

Pre-2.4 budget blocks require explicit renew migration after an authorized engine
upgrade. Preserve all STATE, queue events and Reports; renew reconstructs usage
from retained reports/lease events, with conservative task usage for incomplete
legacy evidence. Do not overwrite an adopted project's engine automatically just
because this plugin is newer; read the project's continuous runbook upgrade notes.
