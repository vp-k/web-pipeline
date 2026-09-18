# Verification scope update — engine 2.8

Task reference: `Docs/Work/WEB-SCOPED-VERIFY/STATE.md` (sole workflow-state owner).
The local conversation explicitly requested the Task impact / Phase integration /
Release full-project split. This kit remains non-ready; delivery tests do not grant
project readiness, protected review acceptance or production permission.

## Design and implementation choices

- Add explicit Task/Phase profiles and opt-in component/check configuration.
  Keep Full/Release project-wide in scoped mode and preserve legacy behavior when
  configuration is absent. Updating the engine does not silently reduce coverage.
- Select real command IDs; do not append guessed test-filter arguments to a broad
  suite. Include transitive dependents, acceptance and connected contracts. Unknown
  paths, ambiguous ownership, broad configuration and protected/T3/T4 changes expand.
  Renames include both source and destination owners.
- Represent each integration phase as a normal tracked task with SCOPE.json.
  Its current verified run reruns the member check union and phase integration
  suites, retaining exact historical member evidence and review/approval bindings.
  All-task gates accept that coverage without separately replaying every member.
- Permit historical member evidence only for scheduling within an explicitly
  queued phase group; final queue/merge completion still requires current phase
  checks and decisions. Missing Baseline, fake DONE, missing review and stale or
  tampered evidence fail closed. Phase dependencies are explicit queue edges.
- Retain STATE's legacy `full_run` field for compatibility. Summaries record the
  exact Task/Phase/Full profile; Fast cannot satisfy completion. Budget history and
  protected standard/strict approval authority retain their original meaning.

Alternatives considered: renaming Full without changing commands would not reduce
cost; file-only test filtering would omit consumers; weakening current-source gates
without a phase rerun would reuse stale evidence. Automatic migration of existing
projects would change an approved policy without a scoped adoption decision.

## Evidence and limits

Pre-change source revision: `daec5869c9101e9bb85781c8e09f3db516121d3a`.
Baseline: `python tests/verify_delivery.py`, 165 tests, zero failures/errors/skips;
[retained report](Reports/Pipeline/delivery-20260912T112922Z-5c81783e/delivery-validation.json).
Final executed evidence is linked from the task's VERIFICATION.md.

The full regression executed 178 cases; the final bundled scope/recovery suite
executed 15, including two added follow-up cases. All passed without skips. The
[generated coverage/integrity audit](Reports/Pipeline/delivery-audit-df52a2a196e0/delivery-audit.json)
matched all 180 unique current engine tests to successful retained executions.
Final packaging executed eight passing cases. Build output is
`dist/package-2.8.0-lf`; its checked-in skill snapshot contains 136 engine assets.
Known UTF-8 text is normalized to LF before hashing; binary assets remain exact.

Declaration and adapter quality still determine semantic coverage. A suite command
that runs the whole project remains broad. Full source integrity remains required
for individual current evidence; historical member reuse requires a current phase.
Archive retains its exact-source capture gate and does not automatically archive
historical members or remove their covering phase. Nested/archived phase members
are intentionally unsupported. No existing installation, adopted project, remote
CI, production system, commit or push is changed by this delivery.
