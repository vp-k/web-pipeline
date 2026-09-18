# Renewable execution budgets (2.4)

## Plan and scope

Implement the user's requested queue/task renew command, append-only budget grants,
active-time accounting, failed-attempt enforcement, timeout classification, schema
compatibility, regression tests, and updated skill/plugin distribution. Preserve
the existing uncommitted 2.2/2.3 work. No target application checkout is in scope;
AICX-000 is a reported example, not a task present in this kit.

## Decisions

- Keep `attempts` as cumulative Fast/Full execution history. In new accounting,
  `total_attempts` config caps failed attempts, not successful verification runs.
  Keep the config key for compatibility; explain its new accounting semantics.
- Effective budgets are original config/plan plus append-only renewal grants;
  never rewrite initial timestamps, baseline limits, revision, or past events.
- `loop renew --queue` and `loop renew --task ID` are separate explicit operations.
  The queue's extra-attempts grants scheduling steps; a task's grants failed runs.
  No trust argument, no manufactured identity, no implicit unlimited renewal.
- A user request to resume may authorize one bounded renewal recorded with that
  request's reason. A generic earlier keep-going request is not permission for
  automatic repeated renewals after limits are exhausted.
- Task time is the sum of Fast/Full summary intervals, including failed runs.
  Queue time is the sum of claimed lease intervals, not time spent without a lease.
  An abandoned lease cannot distinguish work from offline time: recover charges its
  interval conservatively. No daemon/heartbeat or unverifiable idle subtraction.
- Old accounting migrates explicitly through renew, retaining the original block
  and source hashes. Complete retained evidence is used to reconstruct usage;
  incomplete legacy evidence uses documented conservative usage, never zero.
- Time-budget exhaustion stays non-PASS but does not consume external-retry budget.
  Actual execution/spawn blockers retain their separate accounting. Renew never
  resets same_failure, external_retries, approvals, exceptions, or task readiness.
- Interrupted verification retains a pending reservation before execution. Renewal
  may settle its budget from retained evidence or conservative elapsed time; it
  cannot restore a Full pointer, grant approval, or count unknown work as PASS.

## Validation

Baseline: 93 engine tests PASS, zero failures/errors/skips, retained at
`Reports/Pipeline/delivery-20260909T112533Z-1008e1d0/delivery-validation.json`.
The initial targeted run exposed the obsolete wall-age expectation in the existing
elapsed-limit test. It now exhausts active time instead; separate tests demonstrate
idle time is excluded. Rerun: 31 loop/renewal tests PASS in 158.049s; 5 additional
recovery/schema checks PASS in 11.318s. Final full-suite results follow below.

This document is implementation reasoning, not task STATE or a signed human decision.

## Final validation and installation

- Engine: **114 tests PASS**, zero failures/errors/skips, Python 3.13.14, Windows 11.
  Evidence: `Reports/Pipeline/delivery-20260909T114221Z-2744c515/delivery-validation.json`.
  Log SHA256: `1be01cae0e993bd2445548a6549f84e0b6477a0ffcadbdc4fa502645ac02e61a`.
- Distribution: **6 tests PASS**, zero failures/errors/skips.
  Evidence: `Reports/Pipeline/packaging-a79c5a629330/packaging-validation.json`.
- The final bundled engine separately executed 3 renewal/migration smoke cases:
  PASS in 23.134s (not counted again in the 120 distinct regression tests).
- Build: `dist/package-2.4.0-final`; plugin ZIP SHA256:
  `bd6c65fc3e5c714d45c58a5715ccfe84edf52524ce755a757910914966dc8ff9`.
- Refreshed the generated repository skill and personal plugin source. Reinstalled
  `web-development-pipeline@personal`, version `2.4.0+codex.20260909114904`.
  Source/installed doctor verifies 101 bundled files; skill/plugin validators PASS.
- Start a new conversation to load updated skill guidance. Adopted project engines
  are separate: no AICX project, task, budget, config or approval was modified here.
- Remote CI, production operations and new-thread discovery: NOT_RUN. No commit or
  push was performed. Original evidence and previous distribution builds remain.
