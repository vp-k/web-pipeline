# Standalone Web Development Pipeline

Python 3.11+ engine for risk classification, guarded task state, real verification runs, decision records, and protected human approval gates. Ordinary development needs no human name or external trust setup. PowerShell files are thin adapters; they cannot set PASS fields.

Skill/plugin distribution sources and build instructions live in `Packaging/` in the original kit checkout (not copied into adopted projects). The reusable `web-development-pipeline` skill includes an engine bootstrap, while adopted projects retain their own engine and approval boundaries. Installing the plugin does not configure or approve a project.

The ready-to-use, self-contained skill is checked in at [skills/web-development-pipeline](skills/web-development-pipeline/SKILL.md), including its engine assets. After cloning, check it with `python skills/web-development-pipeline/scripts/pipeline.py doctor`. This is a versioned distribution snapshot; maintain the engine and packaging sources, rebuild, then refresh the snapshot together with its asset manifest. Existing personal Codex installations are separate copies and remain unchanged.

## Development scope (2.10.1)

Infrastructure, hosting, deployment and production operations are user-owned.
Unless explicitly requested, the pipeline plans and completes application work
through required local/test verification, review and evidence without making
deployment access or Release readiness a development prerequisite. Explicitly
requested infrastructure/deployment work retains the existing risk and approval gates.

## Planning questions before implementation (2.10)

New/revised tasks require source-backed analysis of goals, user flows, exceptions,
data/integrations, constraints and acceptance in CLARIFICATIONS.json. Ask material
questions during planning, wait for actual answers and reflect them in testable
requirements. Known unresolved questions block preparation and implementation.
`clarification-report --task <id>` is read-only; CLEAR is not readiness or approval.
Legacy unrevised tasks report missing coverage explicitly. See
[planning and late-question handling](Docs/Runbooks/CLARIFICATIONS.md).

## Task, phase and release verification (2.8)

With explicit `verification.scopes`, Task completion runs acceptance and impacted
component/consumer regression. A tracked Phase reruns member checks plus connected
integration/E2E checks. Full/Release cover the configured project. Unknown impact,
broad inputs and protected/T3/T4 changes expand to project-wide verification.
Legacy projects remain on Full until scope configuration is explicitly adopted.

`verification-plan --task <id>` displays selected commands and expansion reasons
without running them. A current verified phase can cover exact historical member
evidence at merge gates; missing reviews, approvals or stale phase source cannot.
See [configuration and executable lifecycle examples](Docs/Runbooks/VERIFICATION_SCOPES.md).
The legacy `full_run` pointer retains its name and binds the actual Task/Phase/Full
summary. This update does not silently install into existing projects.

## Progress versus merge readiness

Ordinary work under standard policy proceeds from the user's scoped request through
implementation, repair, verification and local review without repeated approval
questions. Engine 2.8.2 checks existing valid approvals before asking again; protected
phase decisions still apply. See [approval prompting and reuse](Docs/Runbooks/APPROVALS.md).

Sequential work does not require a branch, worktree or merge. Continuous queues
default to validating only their requested tasks at completion. Set a queue plan's
`completion_gate` to `merge` only when all-active-task merge readiness is part of
the requested work; a failed required gate returns WAITING and prevents starting a
replacement queue. Git conflicts and unfinished integration operations stop new
actions across that checkout. Existing PR/CI policies still apply independently.

Engine 2.7 adds a [real browser/API/SQLite lifecycle](examples/web/README.md),
[structured test-result gates](Docs/Runbooks/TEST_RESULTS.md), and
[read-only adoption previews and recoverable engine updates](Docs/Runbooks/UPDATES.md).
No new identity/trust input is required. Updates preserve project settings, tasks,
approvals and iteration history; they do not silently grant readiness.

Engine 2.6 adds explicit browser/server/shared component boundaries, permitted
imports, source-bound dependency evidence and contract provider/consumer checks.
It does not require separate repositories or a backend for static sites. Configure
real paths and adapters using [the boundary runbook](Docs/Runbooks/BOUNDARIES.md).
The included JS/TS adapter uses project TypeScript; other stacks/framework bridges
need suitable adapters. Existing projects without configuration warn NOT_CONFIGURED;
installation alone does not prove isolation or automatically upgrade them.

Engine 2.5 defaults new adoption to `approval_policy: "standard"`. Unprotected
T0–T2 work can iterate without human signatures. T1/T2 still requires an actual local
review decision bound to current Full evidence; self-review is labelled honestly,
not represented as independent review or human approval. Protected changes, all
T3/T4 work, check exceptions and Release require explicit scoped user decisions,
recorded as local chat receipts without identity/key/trust setup. `strict` remains
available, and existing configurations without this field retain legacy strict.
Plugin updates never silently change an adopted project's policy or engine.

Use `approval-request --task ... --phase design|review|release|exception` to present
the actual scope and binding, then `approve --task ... --record ...` only after the
user explicitly approves. Receipts preserve the user's message, presented context,
conversation reference and exact source/evidence binding; they are not signatures
or proof of identity, organizational authority or independent review. See
[approval receipts and upgrade guidance](Docs/Runbooks/APPROVALS.md).

For continuous, resumable development, use `loop start/status/next/complete/recover/retry/reconcile/renew`. The active skill repeatedly handles implementation, verification failure repair, advisory review and next-task selection until the authorized queue is complete or genuinely blocked/budget-limited. Queue selection and agent decisions are retained with reasons and source/evidence identities. See [continuous operation](Docs/Runbooks/CONTINUOUS.md). This is a host-driven loop, not an unattended background model service.

Engine 2.4 separates usage history from renewable budgets: successful Fast/Full
runs remain in `attempts` without consuming `failed_attempts`. Task time sums actual
verification intervals; queue time sums lease intervals, not idle time since creation.
A user-requested `loop renew --queue/--task ... --reason ... --extra-minutes ...
--extra-attempts ...` appends budget without erasing history or rewriting config.
Queue extra-attempts grants steps; task extra-attempts grants failed runs. Renew
does not need trust and never clears same-failure/external-retry guards, approvals
or exceptions. Time-budget BLOCKED outcomes do not consume external retries.
See the runbook for explicit 2.3 accounting migration and interrupted-run recovery.

`validate` inspects work in progress; its PASS does not authorize merging. Require the explicit merge gate in CI:

```console
python -m web_pipeline --root . validate --gate merge --base-ref origin/main
```

Every active task must be DONE with current completion evidence (or exact member coverage by a current verified Phase) and the applicable local review/user receipts or strict signatures. Supply `--trust` only for required signatures or existing signed records. Merge mode rejects `--kit`, `--task`, and an empty active task set. It is not production deployment authorization.

Acceptance checks are automatically included in Full/Release even when absent from domain defaults. Prepare rejects disabled or Full-ineligible checks. Baseline runs only in DRAFT; returning blocked work to DRAFT requires `revise`, which increments revision without resetting retry budgets. Approved N/A does not count as a failed attempt's failure fingerprint. Verification hosts use explicit script files, not shell command strings.

## Quick start

```console
python -m pip install -r requirements.txt
python -m web_pipeline --root . validate --kit
python -m unittest discover -s tests -v
```

Install without overwrite:

```console
python -m web_pipeline init --target ../my-project
```

The adopted copy deliberately remains `project.ready: false`. Configure all six source documents, a Git/base reference and real argv-based checks before enabling project validation. External trust is needed only at signed gates, not for ordinary standard development. JSON-compatible YAML is required: `pipeline.config.yaml` is JSON syntax and therefore YAML 1.2-compatible without a YAML parser.

Typical lifecycle:

```console
python -m web_pipeline --root . new --task WEB-101 --title "Profile endpoint" --tier T2 --domains backend,api --base-ref origin/main
# Populate BRIEF.md, DOR.md, PLAN.md and ACCEPTANCE.json before preparing.
python -m web_pipeline --root . prepare --task WEB-101
python -m web_pipeline --root . run --task WEB-101 --profile Baseline
python -m web_pipeline --root . transition --task WEB-101 --status READY
python -m web_pipeline --root . transition --task WEB-101 --status IN_PROGRESS
# Implement the scoped change, run Fast, then:
python -m web_pipeline --root . transition --task WEB-101 --status VERIFYING
python -m web_pipeline --root . run --task WEB-101 --profile Full
python -m web_pipeline --root . transition --task WEB-101 --status REVIEW
# Review code and evidence; write choice/rationale/alternatives/risks to decision.json.
python -m web_pipeline --root . review --task WEB-101 --decision Docs/Work/WEB-101/decision.json
python -m web_pipeline --root . transition --task WEB-101 --status DONE
```

This example assumes standard unprotected T2; classification may promote actual changes. Before `prepare`, replace template text in BRIEF/DOR and the tier-required PLAN or EXEC_PLAN, and populate ACCEPTANCE.json with configured check IDs. Protected T3/T4 work also needs accepted ADR records plus scoped design and review decisions (user receipts in standard, signed approvals in strict). Local reviews bind revision, fingerprint, tree and Full report hash; rework needs fresh evidence and review. `prepare` and `loop next` default to execution label `codex`, not a fabricated human name.

`STATE.md` is the sole state owner. Only executed checks can PASS. Release verifies readiness and never deploys. A local writer can modify local code and evidence, so integrity hashes and standard user receipts are audit aids, not an authorization boundary. Strict human gates use Ed25519 signatures with externally protected trust and private keys unavailable to AI. Production needs a separate explicit execution request and actual external permission/environment approval under either policy. A trust file contains public keys; its outside-project location alone is not protection if AI can still edit it.

## Migrating v1

There is no implicit v1 upgrade. Initialize v2 into a clean target, configure v2 facts, recreate/revise tasks, rerun Baseline and Full, and obtain fresh user receipts or strict signatures over the v2 fingerprint and snapshot. Never copy v1 status flags or approval claims as approved v2 records.

See [configuration](Docs/Runbooks/CONFIGURATION.md), [operating model](Docs/Governance/00_OPERATING_MODEL.md), and [example](examples/minimal/README.md).

## Human-operated signing (strict or existing signed records)

`Scripts/sign-record.py` signs a reviewed payload using an existing external Ed25519 private key. Run it only in a human-controlled shell whose key is unavailable to implementation agents:

```console
python Scripts/sign-record.py --payload C:/secure/reviewed-payload.json --private-key C:/secure/human-ed25519.pem --output Docs/Work/WEB-101/review.json
python -m web_pipeline --root . attach --task WEB-101 --kind approval --path Docs/Work/WEB-101/review.json
```

It never generates or prints private keys and refuses to overwrite output. The operator must independently verify identity, role, phase, expiry, scope, fingerprint, conditions, and—on review/release—the tree digest, prerequisite Full run ID, and `run_digest`. Use `attach` to schema-check and reference the repository-relative record. Attach does not approve anything: signature, trust, role, scope, source, tree, and run bindings are enforced at the relevant transition or run. ADRs can be attached only to an unprepared DRAFT; signed approvals/exceptions may be attached later.

Because reports are normally gitignored, strict CI requires an explicit evidence source. On a PR, add `Docs/Work/CI_EVIDENCE.json` containing `{"workflow_run_id":"123456"}` with the actual repository run that uploaded the complete change set's `pipeline-evidence` artifact. Manual/reusable invocations may instead supply `evidence_run_id`. The reference is routing metadata, not approval. The engine still validates fingerprints, source tree, artifact hashes, and signatures bound to Full summaries.

`project-policy.yml` runs on PRs and enforces the merge gate for adopted projects. Only a distributable kit whose base and candidate are both kit mode uses kit validation; downgrading an adopted project to kit mode is rejected. Missing evidence or required approvals fails closed. Standard receipts need no trust secret; strict and existing signed records still require protected trust. Evidence-producing workflows and external authority enforcement remain project-specific. Protect the validator/workflow and require this job; never give privileged deployment credentials to untrusted PR execution.

## Closing a completed change

`Docs/Work` contains the active change set. When a branch/PR integration is part of the workflow, finish that merge first. In a single-checkout workflow, no merge is required solely for archiving. Explicitly archive valid DONE tasks before beginning unrelated code changes, while review decisions and completion evidence still match the current code:

```console
python -m web_pipeline --root . archive --task WEB-101
```

Archive revalidates the task, captures `SOURCE.zip` and `SOURCE_MANIFEST.json` matching the approved Full tree digest, then moves its single STATE and records into `Docs/Archive/WEB-101-r1` without overwriting. Verified uncommitted source is preserved too; Git HEAD is only supplementary provenance. Potential credential files such as `.env` and private key containers block source capture: isolate credentials before verification. Retain the complete archive and original Reports/Pipeline evidence in trusted storage. Archive is historical evidence, not a new approval. Run any intended Release gate first. An archive-only PR still needs a current housekeeping task; an archive cannot substitute for current merge evidence.
