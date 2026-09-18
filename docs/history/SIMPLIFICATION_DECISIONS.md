# Approval simplification (2.3)

## Requested outcome

Ordinary iterative development must not require a human name, signing key, or
external trust path. Preserve truthful evidence, decisions, risk classification,
bounded iteration, and human gates for protected/high-risk work and release.

## Plan

1. Run the existing lifecycle/continuous-loop regression baseline.
2. Add a `standard` approval policy for new adoption. Keep `strict` and interpret
   absent configuration as legacy strict; never silently downgrade an existing project.
3. For standard, unprotected T1/T2 work, require an explicit local review decision
   bound to revision, fingerprint, current tree and Full report. Label this as
   self-review/advisory evidence, not independent human approval. Keep T0 evidence gates.
4. Retain signed design/review gates for all protected or T3/T4 work, signed
   exceptions, and separate multi-human T4 release readiness. No production execution.
5. Integrate local reviews into the durable loop and manual CLI; use `codex` as an
   optional execution label default, not a fabricated human identity.
6. Update guidance, CI trust provisioning, tests, distribution and installed plugin.

## Choices and alternatives

- Two policies (`standard`, `strict`), not a matrix of independent bypass flags.
  Reject disabling all approvals: protected decisions would become self-approved.
- Retain the existing signed backend for human gates. A chat receipt or editable
  JSON checkbox cannot authenticate a human. GitHub/environment approval adapters
  are not implemented or claimed; adding one requires a separate trust design.
- A local review is useful accountable self-check evidence, not independent review.
  Do not force routine work to invent another reviewer or ask the user for a name.
- Require decision rationale, alternatives and risks; bind the record to actual Full
  evidence and reject stale records. Hash binding detects stale data, not a malicious
  writer who controls the entire repository.
- Missing policy stays strict for backward compatibility. Explicit policy changes
  are governed config changes; prepared tasks must be revised and reverified.
- External trust stores contain public keys. Outside-repository placement alone is
  insufficient: protect the store/validator and keep private keys unavailable to AI.

## Validation

Baseline: existing lifecycle + continuous-loop suite executed 27 tests in 159.714s,
all passed. New simplification suite executed 10 tests in 52.933s, all passed:
manual T1 DONE/merge without trust, T2 loop completion, retained decision trail,
legacy strict defaults, all protected/high-risk role gates, auth rejection, stale
and tampered evidence rejection, rework review renewal, and CLI execution labels.

Final full regression: **93 tests PASS**, no failures/errors/skips, Python 3.13.14
on Windows 11. Retained evidence:
`Reports/Pipeline/delivery-20260909T091924Z-e3ebfccb/delivery-validation.json`.
Final distribution regression: **6 tests PASS**, no failures/errors/skips:
`Reports/Pipeline/packaging-2e9e9f791e2e/packaging-validation.json`.
The built package also executed the standard T1 manual and T2 continuous lifecycle
tests directly from its bundled engine: 2 PASS in 28.859s (additional smoke checks,
not included in the 99 distinct full/distribution tests).

Built `dist/package-2.3.0`; plugin ZIP SHA256:
`968698afc04937e580c9f8ba3ce78b745871560e09a6246eedccefb8b2570a46`.
Refreshed the repository's generated standalone skill and personal plugin source;
reinstalled `web-development-pipeline@personal` as
`2.3.0+codex.20260909092525`. Source/installed doctor verifies 98 bundled files;
skill and plugin validators PASS. Start a new conversation to pick up new guidance.

Remote CI and new-conversation skill discovery: NOT_RUN. No production operation,
real human approval, commit or push was performed. Existing adopted projects were
not overwritten. This kit is not an approved production task; this document is not
human approval or STATE.
