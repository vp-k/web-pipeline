# Operate an adopted project

The wrapper accepts a required target followed by the project's CLI arguments:

```console
python "<skill>/scripts/pipeline.py" project --root "<project>" validate
python "<skill>/scripts/pipeline.py" project --root "<project>" validate --gate merge --base-ref <trusted-base>
```

It uses the project's engine. Read its README and applicable runbooks for exact options and schema versions. Do not mix a bundled schema with an adopted project's different engine version.

For authorized tracked implementation:

Before `prepare` on engine 2.10+, read the target's CLARIFICATIONS runbook. Analyze
the six planning areas, ask concrete material questions and wait for actual answers.
Record sources and affected acceptance IDs in CLARIFICATIONS.json; inspect
`clarification-report --task <id>`. Repeated permission avoidance does not authorize
guessing requirements. Late questions follow the blocked/revise/reconcile procedure.

Before the first feature in a newly adopted project, apply the
[adoption stage exit criteria](adoption.md#first-feature-before-expansion).
On resume, inspect existing evidence and continue from the missing stage; do not
repeat setup or add a new first-feature gate to every ordinary task.

1. Select an existing task or create a scoped DRAFT with `new`, including a real comparison base and affected domains. Let classification promote risk. Populate BRIEF, DOR, ACCEPTANCE and tier-required plan/ADR records; do not invent owners.
2. `prepare` seals the documents and implementer. Run Baseline before changing product code while still DRAFT. An executed existing failure may establish a retained baseline, but its report remains FAIL; inspect evidence and baseline_run rather than assuming a nonzero result is acceptable.
3. Obtain required human design approvals and use `transition ... READY`, then IN_PROGRESS. Implement the requested scope, preserving tests and the baseline. Use Fast during iteration within the engine's limits.
4. Read the project scope runbook (engine 2.8+) and inspect `verification-plan --task ...`. Transition to VERIFYING, run Task for scoped work, Phase for a tracked connected group, or Full for legacy projects, and inspect outputs. Completion includes acceptance checks; frontend work requires actual desktop/mobile screenshot evidence and interaction checks. Do not synthesize screenshots or summaries. Test adapters must detect zero tests/skips as required by the actual project.
5. Enter REVIEW only with valid current completion evidence. In standard unprotected T1/T2 work, inspect the changes and record `review --task ... --decision <JSON>` (choice, rationale, alternatives, risks), then transition DONE. This is explicitly self-review/advisory evidence, not independent human approval. Standard protected/T3/T4 requires the user's scoped acceptance of that evidence through `approve`; read [approvals.md](approvals.md). Strict retains signatures. Only a valid engine transition can establish DONE.
6. Sequential work uses the current checkout without a mandatory branch/worktree or merge. When merge readiness is requested, it uses all active tasks and retained original evidence; stop on failure before unrelated work. Existing PR/CI policy remains required. Run Release only for explicitly requested T4 readiness with required approvals; it cannot execute production operations. Archive only when requested and currently valid, after any intended branch/PR integration and before unrelated new source changes; preserve archives and reports.

Phase archival uses `archive --task PHASE-ID --include-members`; connected phases
sharing members move together after all gates pass. Historical member runs remain
historical and their metadata separately binds current integrated Phase source.
A completed referencing queue is retained as history, allowing a later queue to
start without moved states. Failed merge gates and live leases still block archive.
Read `Docs/Runbooks/ARCHIVES.md` for journaled rollback and `archive --recover` after
an interruption; never delete the pending journal to bypass recovery.

For coupled backend/frontend work, use the exact sequence and explicit queue plan
in `Docs/Runbooks/IMPLEMENTATION_GROUPS.md` (engine 2.9+). Risk and verification
impact share the union of boundary and scope dependencies; authorization consumers
must promote risk before implementation. Preserve every required test and gate.

If scope changes after READY, use `revise` and prepare/reverify the new revision. This invalidates stale approvals and evidence but does not reset retry limits. A missing tool, approval or external condition is a blocker to report, never a reason to falsify progress or bypass a gate.
