# Continuous-loop implementation decisions — 2026-09-09

These are the implementation's actual choices and tradeoffs, not human approvals or accepted protected ADRs.

| Choice | Reason | Alternative considered | Residual limit |
|---|---|---|---|
| Active skill plus deterministic queue | Reuses the running agent's tools and permissions while making progression resumable | A background agent/API daemon would require new execution, cost and host-lifecycle contracts | An exited host does not wake itself |
| Queue metadata separate from task STATE | Preserves STATE.md as the only owner of readiness, evidence pointers and DONE | Mirroring task statuses in a queue could create contradictory authorities | Queue cursors must always be reconciled with live STATE/evidence |
| Exclusive token persisted before each action | Prevents cooperating workers from duplicating or acknowledging stale work | Automatic timeout takeover might replay effects of a still-running worker | Hard interruption needs inspection and explicit recovery; arbitrary writers are not isolated |
| Keep existing task limits and add queue limits | Continuous progress must not become unbounded retries or implicit spending | Removing the 5/3/2/120 limits would weaken existing governance | Queue time is checked between actions; in-flight work uses existing runner timeouts. Larger budgets need explicit policy decisions; no hidden reset exists |
| Structured choices plus automatic scheduling reasons | Existing ADR/run logs did not explain routine task ordering and repair choices | Free-form final summaries are incomplete and easy to lose on resume | The engine checks required structure, not reasoning truth; protected ADRs/signatures remain separate |
| Fail closed on stale shared-source evidence | All current Full signatures bind the whole verified tree | Silently reusing a previous task's approval after another task changed source is unsafe | Dependency/task granularity must account for shared-source binding; explicit reconciliation can be necessary |

Verification is recorded separately in the executed test reports. Test-only keys and injected interruption fixtures are not real approval records.
