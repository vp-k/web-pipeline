# Continue authorized work

A stage boundary or diagnostic nonzero exit is not a request for another user
permission. Inspect current STATE, queue and evidence, not an old request file or
handoff note. Resolve causes within the existing request before ending the turn.

| Signal | Agent action | Stop dependent work only when |
| --- | --- | --- |
| ACTION_REQUIRED / CONTINUE | Execute the leased action, complete it and call next | The action exposes a real unresolved decision or external blocker |
| AWAITING_USER | Check actual existing consent; transcribe unchanged scoped consent or repair records, then recheck | A required decision is genuinely missing, changed, withdrawn or unavailable |
| NEEDS_INPUT | REPAIR_RECORD fixes technical record errors; CHECK_EXISTING_REQUIREMENTS checks existing answers before asking | A material requirement remains unresolved |
| FAIL / changes_required | Diagnose, repair and reverify within the request and retry bounds | Repair needs a new scope decision, exception, unavailable resource or exhausted hard guard |
| WAITING / BLOCKED | Inspect dependencies and cached waits; resolve the cause and use normal transitions/retry | No authorized recovery or independently runnable work remains |
| BUSY / interrupted lease | Inspect effects and processes; wait for a live worker, recover only a confirmed abandoned lease | Ownership cannot be established safely |
| Time warning | Continue in warn mode, report actual usage | An enforce-mode budget or a separate hard guard is exhausted without an applicable grant |
| Git conflict/error | Preserve changes and finish the authorized integration before new feature work | A content decision or destructive recovery is not authorized |
| Review tool unavailable | Perform and record a separate local self-review for ordinary standard work | The policy requires human/independent review that is unavailable |

Recovery commands are explicit, auditable operations; "explicit" does not mean
asking again when the current request already authorizes that recovery. Do not
reset usage, replay unknown side effects, weaken checks or substitute an AI review
for a protected user decision. Hard retry/step guards still prevent endless loops.

Optional archival must not become a permission question before every next task.
A user's explicit standing archive request can cover later completed tasks in its
stated scope; validate every archive through the existing gates. Without that
request, do not couple completion reporting to archival. Stale DONE/Phase evidence
and unfinished queues still need legitimate reconciliation; archival cannot hide them.

Group only decisions that are currently reviewable. Retain separate task/phase
records. Design approval does not cover later implementation evidence, exceptions,
Release readiness or production execution. Ordinary standard work has no user
approval gate. Existing valid phase consent never needs a fresh reply merely due
to a new session, role label or missing transcription.
