# Exact implementation order for connected components

Use an explicit implementation group when new provider and consumer code must
both exist before either member's existing completion tests can pass. This changes
scheduling only: Task contract/integration checks stay required and Phase repeats
the connected verification after every member's completion and review.

## Required sequence

1. Define request/response and error contracts, affected component paths, acceptance
   checks and Phase membership. Prepare the tasks and Phase with those exact
   documents before starting the group. Contract changes invalidate fingerprints;
   stop and revise/reconcile the group instead of silently changing the contract.
2. First complete the union of all members' external completion prerequisites.
   Then execute **every member's Baseline** and satisfy its READY and IN_PROGRESS
   gates. No member receives an IMPLEMENT action until all members have entered
   IN_PROGRESS. At the first implementation, their Baselines must bind the current
   common pre-change source. Reserve scheduling for this group's setup and initial
   implementations so unrelated tasks or another group cannot change that source
   between Baselines. Protected work still requires its existing decisions.
3. Implement members in the plan's explicit `order`. With `["API-101", "WEB-101"]`,
   implement API-101, acknowledge its implementation, then implement WEB-101.
   Acknowledgement records work done; it does not declare either task complete.
   No member Fast, Task or review starts until all implementations are acknowledged.
   Before each IMPLEMENT or REPAIR selection, revalidate every member's prepared
   scope, classification, historical Baseline and design decisions. A blocked peer
   or invalid prepared scope stops further implementation. Historical Baselines
   stay bound to the pre-change tree; normal implementation does not replace them.
4. Execute each member's unchanged Fast and Task checks and required review/approval
   gates. Provider, consumer, compatibility and real integration checks remain in
   Task where already required. A failure goes to REPAIR; it is never deferred,
   treated as N/A, or ignored. Existing limits and source-staleness checks apply.
5. Once all members are validly DONE, process the queued Phase. Its implementation
   step is the place for remaining cross-component fixes; its Phase verification
   reruns the member-check union and configured integration/E2E checks against the
   combined source. Queue completion still requires Phase evidence and review.
6. Apply a separately requested merge/release gate when required. Neither a group
   acknowledgement nor plugin installation authorizes production operations.

## Concrete plan

Create `FEATURE-101/SCOPE.json` with
`{"level":"phase","components":["api","web"],"members":["API-101","WEB-101"]}`.
The group starts with DRAFT members and Phase; Baseline may already exist, but
all entry gates run before implementation. Use this queue plan:

```json
{
  "objective": "Implement the agreed feature API and its web consumer",
  "tasks": [
    {"task_id":"API-101","depends_on":[]},
    {"task_id":"WEB-101","depends_on":[]},
    {"task_id":"FEATURE-101","depends_on":["API-101","WEB-101"]}
  ],
  "implementation_groups": [
    {"phase":"FEATURE-101","order":["API-101","WEB-101"]}
  ]
}
```

`depends_on` continues to mean **valid task completion**, not “code exists”. Do
not put API-101 in WEB-101's depends_on inside this group: the explicit order
already requires the API implementation first, and a completion edge would create
a wait cycle. Group registration rejects such edges, omitted/duplicate members,
overlapping groups, missing Phase dependencies and indirect cycles through outside
tasks. Dependencies on previously completed outside tasks remain supported.

An external prerequisite declared only on WEB-101 still blocks API-101's Baseline:
the prerequisite belongs to the whole group for entry scheduling. Once the group
starts setup, unrelated work waits until both initial implementations are acknowledged.
Normal member/Phase verification and completion dependencies remain required.

Plans without `implementation_groups` retain ordinary completion-based scheduling.
Groups are explicit scoped work, not parallel agents or a requirement to use branches
or merge. Only the task's STATE owns its workflow status; group waits are derived
from existing task states, queue cursors and recorded action events.

## Interruption and revision

Complete or explicitly recover any open lease before resuming. A recorded first
IMPLEMENT selection preserves the fact that Baselines preceded the edit, allowing
an interrupted implementation to resume without recapturing a post-edit Baseline.
If group scope changes after implementation began, revise and reconcile the entire
group, including its Phase. Old budgets and approvals are not reset or fabricated.
Never change a cursor or remove group declarations by hand to escape a wait.
