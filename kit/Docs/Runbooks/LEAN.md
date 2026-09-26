# Lean workflow

Lean delivers features with real checks and review, without a task record per change. It applies when `pipeline.config.yaml` has `"workflow": "lean"`. New adoptions default to lean. A missing value means `tracked`.

## Per feature

1. One usable feature is one unit of work. Its schema, seed data, types, API and UI belong together; do not split them into separate units.
2. Write or update tests with the implementation. Never delete, skip or weaken a test to pass.
3. While iterating, run `python -m web_pipeline check --profile Fast` and fix what fails.
4. Before each commit, run `python -m web_pipeline check`. Fix every failure first. Never commit a failing check.
5. Get one fresh-context review of the feature diff, using the `pipeline-reviewer` agent when available. Fix blocking findings and run check again.
6. Commit. The message body contains the `commit_table` from the check output and any user decision the feature relied on.

`check` runs every enabled command whose profiles include the selected profile (`Full` by default). It needs a ready project. Logs and `summary.json` go under the report root, which Git ignores. They are evidence of what ran, not approvals.

## Decisions

`check` lists `decisions`: protected changes that the changed paths imply, such as `database_schema`, `authentication` or `personal_data_pii`. The user decides schema changes, authentication and authorization, personal data, security settings and public API contracts.

- Group every open decision for the feature into one question and ask once.
- Record the answer in the commit message.
- Do not ask again for a decision already given in this conversation or recorded in an earlier commit.

## When a tracked task is required

`check` sets `tracked_required: true` when changed paths classify as T4. Use a tracked task (`new`, `prepare`, Baseline and the flow in `PIPELINE.md`) for:

- payment, wallet and billing changes;
- deployment, release, production data or production operations;
- destructive or irreversible migrations;
- work for which the user asks for audit evidence.

Path rules are hints. If the work is T4 by meaning, use a tracked task even when `check` did not flag it.

## What lean does not create

No `Docs/Work` folders, STATE, fingerprints, approval receipts, resume notes, execution notes or cleanup logs. Planning questions are asked in the conversation; the resulting decisions go into the commit message.

## Failures

Do not rerun an unchanged failing check. Diagnose and fix the cause first. If the cause is outside the project, such as a missing local service, report the blocker in one line and continue other features. A feature whose checks cannot pass is not committed as done.
