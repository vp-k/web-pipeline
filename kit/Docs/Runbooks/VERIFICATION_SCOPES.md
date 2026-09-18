# Task, phase and release verification

Task completion checks acceptance and impacted regression. A phase checks a connected
feature group. Full and Release check the configured project as a whole. This split
changes the selected command IDs, not merely the displayed profile name.

| Point | Profile | Required evidence |
|---|---|---|
| Before implementation | Baseline | Pre-change checks for declared components; unknown scope expands |
| During development | Fast | Component checks and common policy checks |
| Ordinary task completion | Task | Acceptance, affected components and transitive consumers/contracts |
| Connected feature group completion | Phase | Member acceptance/regression union plus integration and E2E commands |
| Explicit full regression | Full | All configured supported domains and every scoped check |
| Release readiness | Release | Full union plus release requirements and existing T4 user gate |

Existing projects without `verification.scopes` retain their existing Baseline,
Fast, Full and Release behavior. Their task completion still requires Full. An
engine update never opts a project into a smaller scope. New adoption should map
real components and commands before readiness. This non-ready distribution kit has
no application layout and does not invent one.

## Configure executable scopes

Add `verification.scopes` to `pipeline.config.yaml` after mapping real components.
The following fragment is an example, not an executable default:

```json
{
  "components": [
    {"id":"web", "paths":["src/client/*"], "domains":["frontend"],
     "depends_on":["shared"],
     "checks":{"Task":["web-unit","web-build"],"Phase":["checkout-e2e"]}},
    {"id":"api", "paths":["src/server/*"], "domains":["backend","api"],
     "depends_on":["shared"],
     "checks":{"Task":["api-unit","api-contract"],"Phase":["checkout-integration"]}},
    {"id":"shared", "paths":["contracts/*"], "domains":["api"],
     "depends_on":[],
     "checks":{"Task":["contract-provider","contract-consumer"],"Phase":["checkout-integration"]}}
  ],
  "task_checks":["lint","typecheck"],
  "phase_checks":["checkout-e2e","checkout-integration"],
  "broad_paths":["build-tools/*"]
}
```

Each check ID must reference an enabled, non-mutating command eligible for Full.
Task/Phase can execute Full-eligible commands; no shell interpolation or automatic
test filtering is introduced. Configure genuinely separate package/suite commands:
an argv that invokes the whole test suite still runs the whole suite. Every scoped
command also runs in project-wide Full/Release, including phase integration checks.
Unconfigured, disabled or unexecutable required commands fail closed.

In scoped mode, `task_checks` and component Task checks replace the legacy domain
Baseline/Fast selection. Put always-required lint/type/build checks in those lists.
Domain Full/Release requirements still define project-wide coverage. Adapters that
produce browser evidence must handle PIPELINE_PROFILE values Task and Phase too.

Paths use case-sensitive repository-relative fnmatch patterns (`*` spans `/`).
Map tests and relevant assets as well as implementation paths. A changed path with
zero or multiple component owners expands the run to project-wide. Common
governance/engine/config/lockfile inputs also expand it. Protected/T3/T4 work always
expands. A component change includes its transitive dependents. Classification
includes their domains and still applies every existing protected/domain risk floor.

When runtime boundaries are configured, component IDs and paths must match between
the two models. Dependency propagation uses both models; touching a contract
includes provider and consumers. Task completion includes contracts involving any
affected participant; Full/Release include every declared contract. The complete
boundary graph remains mandatory even for Fast. This graph scan is not an incremental
cache, and the declarations/adapters still need review and external CI protection.

Frontend Task/Phase retains real desktop/mobile screenshot and interaction checks
where required. Lower cost is not an exception to acceptance or evidence integrity.

## Declare and inspect a task

Before `prepare` and Baseline, create `Docs/Work/WEB-101/SCOPE.json`:

```json
{"level":"task","components":["web"],"members":[]}
```

Declared components provide a pre-change scope; changed files may expand it but
cannot shrink it. Missing scope with no inferred components falls back to Full's
project-wide check union. The scope document participates in the task fingerprint;
editing a prepared scope requires the normal revision and renewed-evidence process.

```console
python -m web_pipeline verification-plan --task WEB-101
python -m web_pipeline run --task WEB-101 --profile Task
```

`verification-plan` is read-only. It shows components, domains, exact check IDs and
expansion reasons. Runs retain this same plan as the hash-bound
`artifacts/verification-scope.json`; gates recompute and validate its selection.
The engine never treats this plan as executed evidence.

Task/Phase use the same bounded iteration accounting as Fast/Full. Continuous
operation selects Task or Phase automatically in scoped projects and Full in legacy
projects. Existing standard/strict review and human approval rules still apply.
Queue plans must declare every phase member as an explicit phase dependency. Within
that authorized group, valid historical member evidence may satisfy scheduling
dependencies while the combined source is being built. It cannot complete the queue
or satisfy merge readiness before the current phase passes.
For schema compatibility, STATE's `full_run` field remains the completion-evidence
pointer; the referenced summary's profile records Task, Phase or Full precisely.
Fast cannot satisfy completion. Explicit Full is accepted as stronger completion
evidence and does not bypass phase membership checks.

For new coupled implementations, use the explicit queue `implementation_groups`
sequence in [IMPLEMENTATION_GROUPS.md](IMPLEMENTATION_GROUPS.md). All member
Baselines/entry gates precede backend/frontend implementation; all implementations
precede member Fast/Task/review, then the Phase runs. This removes completion wait
cycles without dropping any existing contract/integration check from Task.

## Complete a connected phase

Create a normal tracked task with BRIEF, DOR, acceptance, and any tier-required plan
and approvals. Its SCOPE.json describes ordinary member tasks, for example:

```json
{"level":"phase","components":["web","api"],"members":["WEB-101","WEB-102"]}
```

Use `run --task CHECKOUT-PHASE --profile Phase` at its verification step. Phase
completion requires each member to have actual DONE state, valid historical
completion evidence and its original review/approvals. It reruns the union of
member checks and acceptance plus configured phase integration checks against the
current combined source. A member exception is not automatically an exception for
the phase. Fake DONE, missing reviews, stale fingerprints or tampered logs cannot
be covered. Nested phases and archived members are not supported; keep members
active through their integration gate.

A phase's STATE.md is its sole workflow-state owner. Scope documents and reports
do not independently declare readiness. At all-task validation/merge gates, a
current DONE phase can cover its exact historical member evidence. This avoids
rerunning each member separately just because subsequent tasks changed source.
The phase binds member revisions, fingerprints and summary hashes. Changed members,
review rework, a stale phase source snapshot or missing phase approval removes that
coverage. Ordinary tasks without a covering phase retain exact current-tree checks.

Release runs the project-wide union regardless of the task's selected components;
it still requires a DONE T4 task and the separate scoped release decision. No
production command, deployment permission or protected-decision exception is added.

Archive a Phase and its members with `archive --task CHECKOUT-PHASE --include-members`
after explicitly requested archival and successful integration. Connected phases
sharing members move together; every phase must have current valid completion.
Historical member runs retain their original identity. Their archive metadata
separately binds the covering Phase run and the current integrated source bundle;
it never claims to reconstruct the member's old source bytes. Ordinary archives
retain exact completion-source capture. See [archive and recovery](ARCHIVES.md).
