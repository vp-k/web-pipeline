# Standard approval receipts (2.5)

## Authorized scope and plan

The user requested removing identity/key/trust setup from standard protected work
while preserving explicit human decisions. This changes the kit and distributable
skill/plugin, not any adopted application's state or approval records.

1. Capture the existing regression Baseline.
2. Add a source-bound approval request/receipt path for standard policy; keep the
   strict signature verifier and all classification/evidence gates.
3. Test protected T3 readiness, review, T4 release-readiness, stale bindings,
   conditions, exceptions, and rejection under strict/legacy policy.
4. Update governance and agent instructions, build the distribution, verify it,
   and refresh the existing personal plugin through its normal install flow.

## Decisions

- A standard receipt records the actual user message and the scope presented to
  that user, not an invented human identity or an AI signature. Roles are decision
  responsibilities, not authenticated accounts. One user may cover those roles.
- Requests carry task, revision, fingerprint, phase, roles and protected scope.
  Review/release also carry the exact Full run and tree/summary hashes. Recording
  must reject stale requests instead of binding an old message to new work.
- Chat provenance is an agent-transcribed local audit record. It is not proof of
  the speaker's identity, organizational authority, independent review, or
  tamper resistance against repository writers. Strict remains the authenticated
  signature option; missing policy remains strict.
- Design approval never satisfies review, check exceptions or release readiness.
  Conditions require existing hash-bound PASS evidence. Exceptions remain
  check-specific, reasoned NOT_APPLICABLE, never manufactured PASS.
- Release is non-production readiness only. Neither a receipt nor DONE grants
  permission to deploy, mutate production data, rotate secrets, or run a destructive
  migration. Those require a separate explicit execution request and real external
  permission/environment approval, and are not executed by this engine.
- No automatic conversion of existing approvals, no reduction in risk tiers, no
  counter resets, no changes to other projects. Engine upgrades must be explicit;
  prepared adopted tasks require revision/revalidation when governed inputs change.

## Validation

- Baseline: 114 tests PASS, zero failures/errors/skips,
  `Reports/Pipeline/delivery-20260909T125736Z-bc032429/delivery-validation.json`.
- Initial new protected-receipt suite: 15 tests PASS, including actual T3 lifecycle,
  resumed queue, T4 Release readiness, exceptions, stale bindings and strict denial.
- An existing signed-trust test initially failed because it tried to validate trust
  without a signed candidate under standard. It now attaches its signed candidate
  before testing the same outside-project and independent-review boundaries; those
  assertions are preserved. The old authentication test still rejects missing user
  decisions, now with the standard missing-approval diagnostic rather than trust.
- Distribution: 6 tests PASS, zero failures/errors/skips,
  `Reports/Pipeline/packaging-088d9cc0d032/packaging-validation.json`.
- Three built-bundle smoke cases PASS: T3 READY/DONE, continuous queue approval
  recovery, and strict/legacy refusal. These repeat cases, not additional distinct
  regression coverage.
- Canonical/built/installed skill validation and plugin validation PASS. Doctor
  validates 105 bundle files. Installed and enabled
  `2.5.0+codex.20260909131901`; unrelated app plugin and marketplace entries unchanged.
- Standalone distribution refreshed from `dist/package-2.5.0/`.
- Full engine regression: 129 tests PASS, zero failures/errors/skips,
  `Reports/Pipeline/delivery-20260909T131506Z-155be378/delivery-validation.json`.
  Completed 2026-09-09T13:26:53.120471Z; log SHA256
  `11530a82739ba5d76cbada563a87dc74f833ea64f8f913fd2ceef0eff7a59f3e`.
- Total distinct regression cases: 129 engine + 6 distribution = 135 PASS.
  All 105 bundled files match their canonical source bytes. Compilation and root
  kit validation PASS; kit readiness is not application readiness.
- New-thread discovery, remote CI and a real adopted-project migration remain
  NOT_RUN; no claim that AICX-000 is unblocked. The target path was requested.

No actual project approval has been created by this change. Fixture messages and
signing keys exist only in isolated tests. No project engine/state or budgets are
silently upgraded, and no commit, push or production operation is implied.
