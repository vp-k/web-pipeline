# Verification Policy

## Outcomes

Only an executed, conclusive, successful check is PASS.

| Outcome | Meaning |
|---|---|
| PASS | Executed and met the criterion |
| FAIL | Executed and did not meet it |
| NOT_RUN | Was not executed |
| BLOCKED | Could not execute due to an unresolved dependency |
| NOT_APPLICABLE | Irrelevant with a recorded reason and, when important, approval |
| INCONCLUSIVE | Executed but did not establish success or failure |

## Profiles

- Policy: document/state validity, protected classification, ADR fingerprint, secret/dependency rules.
- Baseline: pre-change lint, typecheck, unit, contract, integration, E2E, and build where configured.
- Fast: format, lint, typecheck, affected unit and contract tests.
- Task (scoped projects): acceptance and impacted component/consumer regression checks.
- Phase (scoped projects): member acceptance/regression union plus connected integration/E2E checks.
- Full: all applicable unit, contract, integration, browser E2E, build, smoke, and evidence checks.
- Release: Full plus security, dependency audit, migration dry-run, rollback validation, performance, production-build packaging, and non-production deployment-readiness smoke checks as applicable. It never performs a production operation.

The configured command list is project-specific. A command marked required but disabled or unset is a policy error.

Opt-in `verification.scopes` narrows completion runs; see [scope configuration and phase gates](../Runbooks/VERIFICATION_SCOPES.md). Task completion uses Task, a tracked phase uses Phase, and Full/Release cover the configured project. Unknown/ambiguous impact, broad inputs and protected/T3/T4 work expand to project-wide checks. Existing configurations without scopes retain Full completion. Phase coverage validates exact historical member evidence only after current combined-source checks and required review/approvals pass; it is not a cached PASS.

Task/Phase/Full/Release also execute the check IDs in the task's ACCEPTANCE.json. Prepare rejects disabled or Full-ineligible acceptance checks; scoped profiles can execute Full-eligible commands. The Policy profile calls the common state/risk policy validator before executing its configured commands; a policy failure cannot become a successful Policy run.

## Existing Baseline failures

A Baseline may record an existing regression without pretending it passed. A domain check that really executed with a nonzero exit code and retained, hash-bound logs can be captured as `baseline_run`; its summary remains FAIL and the CLI still exits nonzero. Check the recorded state before proceeding to READY. Policy failures, missing/disabled/blocked checks, timeouts without conclusive exit evidence, source mutation, and integrity failures cannot establish a Baseline. Scoped user receipts (standard) or signed check exceptions (strict) are validated separately. Full and Release still require successful evidence or valid authorized exceptions; an old Baseline failure never excuses a new Full failure.

## Browser evidence

Configured [runtime boundaries](../Runbooks/BOUNDARIES.md) require a source-bound
dependency graph in every profile. Full/Release additionally require all declared
provider, consumer, compatibility and integration checks. Graph coverage, hashes
and policy are revalidated at gates. A complete graph with a preexisting forbidden
edge can establish a FAIL Baseline even when the adapter exited zero: the engine's
semantic violation is retained. Missing or invalid graph evidence cannot do so.
Projects without boundary configuration report NOT_CONFIGURED, not isolated PASS.

Frontend Task/Phase/Full/Release verification requires `screenshots/manifest.json` entries for desktop and mobile unless a valid authorized exception applies. Each entry declares a run-relative path, kind, URL, width, and height. The engine decodes the referenced image and requires its actual dimensions to match both the manifest and configured viewport; filenames are not evidence. Interaction E2E and screenshots prove different things. Browser commands receive `PIPELINE_EVIDENCE_DIR`.

Generated evidence lives at:

```text
Reports/Pipeline/<RunId>/
  summary.json
  logs/
  screenshots/
  junit/
  artifacts/
```

## Iteration

Default bounds are 5 failed Fast/Task/Phase/Full runs, 3 repeats of the
same substantive failure fingerprint, 2 external retries, or 120 active verification
minutes. `attempts` retains every run, including PASS; the compatibility config key
`total_attempts` caps `failed_attempts`. A pending interrupted run is reserved as
non-PASS until evidence settles it. Active time sums Fast/Full summary intervals,
not wall time since the first run. Baseline/Policy/Release retain their phase gates
and command timeouts; they do not spend the Fast/Full failed-run budget.

New adoption defaults to `time_budget_mode: warn`: cumulative time produces a warning, not a stop or another permission prompt. Missing mode in older configurations retains enforce. Individual command timeouts remain effective. Reaching an enforced limit pauses automatic work. User-requested `loop renew --task ...`
appends additional minutes/failed-attempt budget without rewriting initial limits,
past usage or source fingerprints. Revision preserves all budget history. Renew
does not reset same-failure/external guards, approve exceptions, or grant readiness.
There is no reset API. Old accounting migrates explicitly through renew with its
original block and evidence hashes retained; see the continuous runbook.

Time-budget exhaustion remains BLOCKED/non-PASS. A conclusive budget-only result
refunds its reserved failed attempt; mixed or unknown failures do not. It does not
consume external retries or clear the existing same-failure sequence.
Actual spawn/execution blockers still consume external retries. Command timeout
independent of the overall time budget remains a real failed check.

Valid authorized NOT_APPLICABLE outcomes are excluded from failure fingerprints. Successful runs clear the consecutive-failure count. Duplicate or invalid run IDs are rejected before incrementing attempts or clearing existing Full/Release pointers.

The engine checks process exit and evidence integrity, not semantic test coverage.
The engine optionally validates structured per-case test results, minimum executed
tests, skip allowance and required groups at execution and gates; see
`Docs/Runbooks/TEST_RESULTS.md`. Missing/invalid results cannot pass configured
checks. Legacy commands without `test_report` remain exit-code-only; trustworthy
framework reporters and review are still required to detect removed/weakened tests.
