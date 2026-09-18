# Delivery hardening plan

Requested order: CI normalization -> real web lifecycle -> test-result verdicts
-> simpler adoption and safe project updates. This is kit development, not an
adopted application's STATE or a claim of protected human approval.

## Scope and sequence

1. Diagnose the zero-job GitHub failure on commit 1b52256. Validate both workflows
   locally, preserve all test matrices, push only a dedicated verification branch,
   and inspect actual remote jobs. Do not change visibility, billing, credentials
   or branch-protection settings. Retain failures and external blockers honestly.
2. Add a self-contained loopback-only browser + Node API + SQLite example with real
   provider/consumer/compatibility, denied requests, persistence and desktop/mobile
   browser evidence. Exercise Baseline, bounded repair, pause/resume and completion
   for an unprotected scoped task; never manufacture protected approvals. This
   plain-JS reference does not claim Next/Vue adapter coverage.
3. Add optional structured test-report policy to test commands only. Require actual
   executed cases, zero failures/errors, bounded skips and required groups; reject
   absent/malformed/stale evidence. Revalidate at gates. Build/lint commands stay
   separate. Existing project policy is not silently rewritten.
4. Add read-only project diagnosis and upgrade preview with explicit apply/recovery.
   Detect modified managed files; preserve config, product code, governance, tasks,
   receipts, evidence, budgets and user edits. Unknown old installations need an
   explicit baseline package, never trust guessed original hashes. No live adopted
   project is upgraded as a side effect of plugin installation.
5. Run regressions and real example, rebuild distribution, validate and refresh the
   standalone skill/local plugin through the creator tools. Record concrete results.

## Deliberate choices

- Keep the reusable engine language-neutral. Demonstrate one runnable web stack
  before claiming support for additional frameworks.
- CI verification branches are scoped implementation artifacts, not production
  deployment or an implied request to merge main.
- Prefer one compact normalized result format and real adapters over exit-code
  guesses or fabricated checks. Counts alone do not establish semantic coverage.
- Upgrades are explicit file transactions, not permission or budget resets.
- Do not extract a cross-domain Core or add human identity/trust requirements.

## Evidence

Concrete executed results follow; pending checks are not PASS.

Workflow diagnosis: actionlint v1.7.12 reports that `matrix` is unavailable in
step-level `shell` at kit-checks.yml:41. Replace dynamic shell selection with two
literal-shell steps selected by `if`, preserving the original matrix and both
PowerShell test paths. Add workflow lint as an executed CI job. Reference:
https://docs.github.com/en/actions/reference/workflows-and-actions/contexts

First repaired remote run: 34567020596 created all eight jobs. Workflow lint,
boundary adapter and both PowerShell jobs passed. Linux Python 3.13 exposed a
same-size/same-timestamp Python bytecode collision in the renewal regression;
three sibling matrix jobs were cancelled by fail-fast. A deterministic forced
mtime/size collision reproduces a false PASS locally. Isolate Python bytecode per
verification run and assert both historical statuses in the renewal test. Disable
matrix fail-fast so every platform reports its result; do not skip failing tests.

Pre-change engine Baseline: 144 PASS, no errors/failures/skips, report
`Reports/Pipeline/delivery-20260911T053919Z-7a48f422/delivery-validation.json`.
The long wall interval includes a host/tool suspension and is not a performance
benchmark. No task or queue usage was reset.

Repaired remote CI run `34584363399`: all eight jobs PASS, including all four
Windows/Linux Python combinations and both PowerShell adapters.

Real web lifecycle before structured verdicts:
`Reports/Pipeline/web-example-d77998a58b0f/example-validation.json` PASS.
After structured verdicts:
`Reports/Pipeline/web-example-26e7f2de0750/example-validation.json` PASS.
Both retain the deliberate failed Fast run and successful Baseline/Full plus task
completion evidence. Desktop/mobile screenshots are real browser captures; the
mobile capture was visually inspected. This is a local demo, not production auth.

Node 22.15's mandatory-prefix `node:sqlite` is absent from the old builtinModules
list: use Node's exact isBuiltin predicate, with unknown-module rejection tests.
Run the demo server in a native child process to avoid test-loader interception of
SQLite, and accept the non-loading `require.main` guard in the reference analyzer.

Structured-result parser/gate regressions: six PASS. Initial maintenance suite:
nine PASS, including byte-preserving preview, legacy baseline requirement, conflict
protection, interrupted apply recovery and post-upgrade edit/backup checks. Full
regression and distribution/remote verification must still cover the final tree.

Remote run `34586527738` exposed a Windows 8.3 alias bug in managed inventory:
the caller's `RUNNER~1` root was compared against safe_path's expanded
`runneradmin` paths. Canonicalize the inventory root before deriving relatives,
and make injected-interruption tests compare canonical destinations. A portable
relative-root regression exercises the same canonical/uncanonical mismatch. Run
maintenance cases early in CI, retain the entire suite, and keep both PowerShell
matrix jobs running even when one fails. This failure is not an approval or PASS.
