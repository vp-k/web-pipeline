# Archive and recovery

Archive only when the user requests it, after intended integration and before
unrelated source changes. An explicit standing request may cover later completed
tasks in its stated scope; do not ask again for each task. Optional archival is
not a condition for completion reporting and must not be bundled into a required
review approval question. Every archive still passes the existing gates. It moves the sole task STATE into historical storage;
archived evidence is never current readiness. Existing task IDs cannot be reused.

`archive --task WEB-101` validates ordinary DONE work and captures its exact
completion-source bytes. `archive --task CHECKOUT-PHASE --include-members`
validates and moves the Phase and members together. Phases sharing members form
one connected group; all must be completed and current. An unfinished connected
phase blocks archive without moving anything. Omitting `--include-members` rejects
an operation that would leave a phase referring to a moved member.

Member archive metadata version 3.0 retains the historical completion snapshot and
run IDs, and separately records `phase_coverage` with the current Phase summary
hash, revision, exact member binding and integrated source digest. Its SOURCE.zip
contains that verified integrated source, not the member's old checkout. Phase and
ordinary archives retain version 2.0 exact completion-source bundles. Original run
logs, reviews and approval receipts remain in their original reports/documents.

A queue referring to any archive target must be complete, have no active lease,
and satisfy its requested completion gate. Its unchanged checkpoint moves to
`Docs/Work/AUTOPILOT-<queue_id>.json` as history and the active checkpoint is removed
in the archive transaction. Failed merge readiness, unresolved Git integration or
incomplete tasks still block archive. Starting a new queue then needs no old active
STATE. This does not perform a Git merge or create approval.

All target paths and evidence are checked before source capture or moves. Multiple
directory renames use a durable `Docs/Work/ARCHIVE_PENDING.json` journal. On an
ordinary failure, the engine restores moved directories, the queue, and removes
only its generated outputs. After process interruption, inspect the journal and
processes, resolve any stale engine lock only after verifying its process is gone,
then run `archive --recover`. Recovery validates state/output hashes before moving
anything; changed files or ambiguous owners require investigation. Pending archive
recovery blocks task-state reads, policy gates and engine mutations. Recovery is
rollback, not permission to skip revalidation. A failure during source capture
before a move journal exists leaves active states in place; inspect any newly
generated outputs before retrying, never overwrite an existing archive.
