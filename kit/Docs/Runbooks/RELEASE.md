# Release Runbook

The engine's Release profile verifies local/non-production readiness only. It contains no production deployment or production migration executor. Those T4 operations remain separately authorized external procedures.

Before release, require:

- current prerequisite completion evidence (Task/Phase/Full, with protected/T4 work expanded to project-wide checks) and Release-profile evidence;
- phase-specific user receipts in standard, or signed release approvals in strict, bound to the current fingerprint, tree digest, prerequisite completion run ID, and SHA256 of the completion `summary.json` bytes;
- deployment and migration order;
- rollback or restore/recovery procedure;
- observability, smoke checks, and stop thresholds;
- approval covering Release Owner and affected domain responsibilities; strict additionally authenticates identities and independent signers.

Record proposed version/commit, target environment, recovery plan, and readiness evidence in `RELEASE.md`. Do not claim an actual deployment result unless a separately authorized production system supplies it. Never place credentials in the record.
