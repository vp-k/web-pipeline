# Explicit v1 to v2 migration

Version 1 task state, PASS fields, approval text, fingerprints, and run reports are not valid v2 authority. Do not edit a v1 file until it resembles v2 and do not carry approval status forward.

1. Install v2 into a clean target; the installer aborts before copying if any destination conflicts.
2. Configure the six source paths, Git/base reference, argv checks, requirements, report root, and supported domains.
3. Keep `project.ready` false until those facts validate.
4. Recreate each active task, preserving historical v1 files only as clearly labelled, non-authoritative archive material.
5. Reclassify from current paths and policy, populate acceptance criteria, and rerun Baseline and Full.
6. Obtain fresh decisions/reviews for the v2 revision and fingerprint: user receipts in standard or Ed25519 signatures in strict. Review/release records additionally bind the current tree digest, prerequisite Full run ID, and SHA256 of its `summary.json` bytes. Register each record explicitly; registration alone does not establish readiness or prove human authority.

No script silently migrates approvals because an old identity string or PASS flag cannot prove authorization.
