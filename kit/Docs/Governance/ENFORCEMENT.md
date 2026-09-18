# Enforcement Setup

Documentation expresses policy; repository and environment controls enforce it.

## Repository controls

- Protect the default branch and require pull requests.
- Require the pipeline policy job and project verification jobs.
- Require current reviews after new commits.
- Configure CODEOWNERS with real team identities for security, data/migrations, public contracts, infrastructure, and deployment files.
- Prevent force pushes and branch deletion on protected branches.

This kit does not generate CODEOWNERS identities because invented owners provide false accountability.

## Environment controls

- Do not expose production database or deployment credentials to implementation agents.
- Use separate least-privilege credentials for local, test, staging, and production environments.
- Put production environments behind human approvals and auditable short-lived credentials.
- Separate migration execution permission from migration-file authoring permission.
- Protect signing keys, payment credentials, DNS/CDN/WAF access, and secret rotation behind their domain owners.

## CI controls

Scoped projects may use current verified Phase evidence to cover exact historical
member Task runs. Retain every member run and its reviews/approvals together with
the phase report. A Phase is not an exemption from merge validation or Release's
project-wide checks; missing, stale or invalid coverage fails closed.


- Pin or approve third-party CI actions according to organizational policy.
- Retain test logs, JUnit results, browser screenshots, build outputs, and release records for an explicit duration.
- Treat NOT_RUN, BLOCKED, NOT_APPLICABLE without authorization, and INCONCLUSIVE as non-passing.
- Run contract tests on both provider and consumer changes.
- Protect boundary configuration/adapters and require their graph and integrated
  contract evidence; see [BOUNDARIES.md](../Runbooks/BOUNDARIES.md). A local writer
  can forge omitted edges, so hashes alone are not an enforcement boundary.
- Ensure release jobs consume the exact artifact that passed verification.

`validate --kit` is only for the distributable, intentionally non-ready kit. Adoption (`init`, exposed by the plugin as `/web-pipeline:adopt`) creates a project copy with `project.mode: "project"` and `project.ready: false`; `--ci` additionally copies `.github/workflows/project-policy.yml`, which is otherwise not installed. Configure sources, Git/base ref, generated-output exclusions and commands; provision external trust only when a strict signed gate requires it. Then set `ready: true` and make `project-policy.yml` (which runs `validate --gate merge` for a project and falls back to `validate --kit` only for a non-project checkout) a required check on the protected branch.

Engine upgrades rewrite only `web_pipeline/`, `Schemas/` and receipt-listed files under `Scripts/`; the workflow file, `PIPELINE.md`, `Docs/`, `Templates/` and the config are not touched, so compare them against the new kit deliberately (see [UPDATES.md](../Runbooks/UPDATES.md)). Path rules classify `.github/workflows/*` as protected infrastructure (T3), so editing the workflow is itself a gated change.

Reports are normally gitignored. Strict CI may download the named `pipeline-evidence` artifact from an explicit authenticated workflow run ID. Repository Actions permissions, artifact provenance and retention remain enforcement boundaries; after download, engine validation checks the run summary, logged artifacts, hashes, current source binding, and signed-record run digest.

The PR-triggered project job runs `validate --gate merge`, not progress validation. PRs read a positive numeric `workflow_run_id` from `Docs/Work/CI_EVIDENCE.json`; manual/reusable calls can provide `evidence_run_id`. Upload the full change set's original reports as `pipeline-evidence` from that run. Protect this reference and the validator/CI files via actual repository policy. Missing artifacts, required trust, or DONE evidence blocks the gate. Standard user receipts do not require a trust secret; they do not authenticate the speaker or independently enforce organizational authority. Fork/permission limitations are not reasons to expose privileged secrets or bypass validation.

When using a branch/PR workflow, merge completed active tasks before archiving them. Single-checkout task completion does not create a merge requirement; configured PR/branch protections remain effective. The next change set may include archival housekeeping; archive-only PRs need their own active task. Archives retain SOURCE.zip plus a manifest bound to the approved Full tree, but historical archives do not satisfy a new change's merge gate.
