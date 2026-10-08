# Lean workflow

Lean delivers features with real checks and review, without a task record per change. It applies when `pipeline.config.yaml` has `"workflow": "lean"`. New adoptions default to lean. A missing value means `tracked`.

This file is the only source of the lean rules. `PIPELINE.md`, the plugin skill and the `/web-pipeline:check` command point here instead of repeating them.

## A whole project: the feature backlog

When the user asks for a whole project, list its features in build order before writing code:

```console
python -m web_pipeline feature add "Sign-up with email confirmation"
python -m web_pipeline feature add "Profile page"
python -m web_pipeline feature list
python -m web_pipeline feature next
```

- The backlog is `Docs/Work/FEATURES.json`. It records order and progress; it grants no approval and replaces no review.
- `feature next` starts the first `TODO` feature and records the commit it started from. If a feature is already `ACTIVE`, it returns that one, so a new session resumes where the last one stopped.
- `feature done` finishes the active feature. The newest `Task` or `Full` check that started after the feature started must be `PASS` and must not set `tracked_required`. It must still match the code and the whole `pipeline.config.yaml`: an edit or a configuration change after it means run check again. It must also have compared from the commit the feature started from, so a check with a later `--base-ref` cannot finish the feature. `Fast` is iteration, not completion. `commit_gate` in `status` reports this same decision before you run `feature done`.
- Commit `FEATURES.json` with the feature it finished, then run `feature next`.
- `status` shows the active and next feature. The backlog is outside changed paths and the tree digest, so editing it never widens a check or changes evidence.
- `feature` is refused in a tracked project, which plans work as tasks and a loop queue.

A single requested feature needs no backlog; follow "Per feature" directly.

## Per feature

1. One usable feature is one unit of work. Its schema, seed data, types, API and UI belong together; do not split them into separate units.
2. Write or update tests with the implementation. Never delete, skip or weaken a test to pass.
3. While iterating, run `python -m web_pipeline check --profile Fast` and fix what fails.
4. Before each commit, run `python -m web_pipeline check`. Act on its output as "Reading the check output" says. Never commit a failing check.
5. When `commit_gate` in `status` is `ready`, get one fresh-context review of the feature diff, using the `pipeline-reviewer` agent when available. Give it the feature, the gate check's `test_changes`, `weakened_checks`, `notices` and `decisions`, and the user's answers to those decisions. The reviewer reads `commit_gate` and that check's summary; it never runs check. Fix blocking findings and run check again.
6. With a backlog, run `feature done`.
7. Commit. The message body contains the `commit_table` from the check output and any user decision the feature relied on. Keep its `Not enabled` line.

At the start of a session, or after the conversation was summarized, read `last_check` and `commit_gate` in `status` before running anything. A `ready` gate does not need another check.

## What check runs

- `check` without `--profile` runs `Task` when `verification.scopes` declares components and `Full` otherwise.
- `check --profile Task` runs the selection a tracked Task run would make for the changed paths: the `Task` checks of the affected components and of every component that depends on them, `task_checks`, the dependency and contract checks, and the checks the protected changes require. The output `scope` names the level, the components and the reasons.
- A broad input (`broad_paths` and the built-in ones such as `pipeline.config.yaml` and lockfiles), an unowned or ambiguous path, and a T4 change make the Task check project-wide; it then runs exactly what `Full` runs.
- A Task check covers what changed and what consumes it. Run `check --profile Full` once before a release or a merge.
- `check --profile Full` runs every enabled command whose profiles include `Full` or `Policy`.
- `check --profile Fast` runs the enabled policy checks and the `Fast` requirements of the supported and changed domains. A project-defined check that no requirement names follows its own profiles.
- A lean project starts with the checks it has enabled. A required check that is not enabled is listed in `missing_checks` and in the `Not enabled` line of the commit table. Enable it with a real command when the tool exists; never wire a placeholder that always passes.
- With no enabled check for the profile, `check` fails. `status` lists `missing_checks` for the whole project: the checks every supported domain requires that are not enabled.
- A command with a `test_report` passes only when its report exists, is valid and meets its own `min_tests`, `max_skipped` and `required_groups`. A zero exit alone is not test evidence. The reason is written to the check's log.
- In a lean project, a component may leave its `Phase` checks and `phase_checks` empty; lean has no Phase run. A tracked project needs both.

The base of the comparison is the commit the active feature started from, otherwise `HEAD`; `--base-ref` overrides it. A commit inside a feature therefore does not hide its earlier changes from the check or the review. Changed paths, test changes, script changes and the configuration are compared at the merge-base of that base and `HEAD`, reported as `base_commit`, so commits that landed on a base branch later are not counted as this change.

`check` needs a ready project. Logs and `summary.json` go under the report root, which Git ignores. They are evidence of what ran, not approvals.

## Reading the check output

The engine decides these facts by script. Act on them instead of rediscovering them.

| Field | Meaning | What to do |
| --- | --- | --- |
| `status` | `PASS` only when every selected check passed | On `FAIL`, fix the checks `next` names. Never commit a failing check |
| `repeat` | The newest earlier run of the same profile on the same tree, the same whole `pipeline.config.yaml` and the same `base_commit` | A failing `repeat` proved nothing new. Change the code before the next check, or name the environment change that justifies a rerun |
| `same_failure` | Runs, this one included, that failed the same way with no pass of a profile at least as wide between them. A `Fast` pass after a failed `Full` does not end the count | At `iteration_limits.same_failure` (default 3), stop trial edits. Find the root cause in the log, or ask the user |
| `test_changes` | Test files deleted, skip or only markers added, tests removed since the base | The review confirms each one. A test change is never how a check passes |
| `weakened_checks` | Check configuration made weaker since the base | A user decision; see below |
| `notices` | Changes the review confirms | See below |
| `decisions` | Protected changes the paths imply | A user decision; see below |
| `tracked_required` | The paths classify as T4 | Move that work to a tracked task |
| `commit_table` | The check results in commit form | Put it in the commit message |
| `warnings` | Inputs the check could not read, such as a diff or a base configuration of another shape | Review that part by hand |

`status` repeats the newest run as `last_check`: its result, the failing checks, `repeat`, `same_failure`, `test_changes`, and `current`. `current` is true only while the tree and the whole `pipeline.config.yaml` match the run; a summary from an engine before 2.17 is never current.

`status` also shows `commit_gate`, the decision `feature done` applies now. It names the gate check's `run_id`, `profile` and `base`, sets `ready`, and gives the `reason` when it is not ready. The gate check is the newest `Task` or `Full` check since the active feature started, or the newest one at all without an active feature. A `Fast` run after it does not change the gate. The review approves only a `ready` gate.

## Decisions

`check` lists `decisions`: protected changes that the changed paths imply, such as `database_schema`, `authentication` or `personal_data_pii`. The user decides schema changes, authentication and authorization, personal data, security settings and public API contracts.

- Group every open decision for the feature, including `weakened_checks`, into one question and ask once.
- Record the answer in the commit message.
- Do not ask again for a decision already given in this conversation or recorded in an earlier commit.

## Notices and weakened checks

`notices` name changes that the review confirms; they do not raise the tier or need a user decision:

- dependency manifests and lockfiles: review each added or upgraded package. A major framework or SDK upgrade is still a `major_framework_sdk` decision;
- environment files: no real secret or credential value is committed;
- seed and fixture data: no real personal data;
- a check whose `argv` or `cwd` changed, and a `package.json` script that an enabled check runs, with its `pre` and `post` scripts: the check still runs the same tests;
- `pipeline.config.yaml`: see `weakened_checks`.

`weakened_checks` compares `pipeline.config.yaml` with its version at the base. It lists a disabled or removed check, a profile removed from an enabled check, a removed or loosened `test_report`, a requirement or policy check removed, a supported domain removed, and a removed or changed protected path rule. Each one is a user decision: ask it with the other decisions and record the answer in the commit message. Never weaken a check to make a failing feature pass.

## When a tracked task is required

`check` sets `tracked_required: true` when changed paths classify as T4. Use a tracked task (`new`, `prepare`, Baseline and the flow in `PIPELINE.md`) for:

- payment, wallet and billing changes;
- deployment, release, production data or production operations;
- destructive or irreversible migrations;
- work for which the user asks for audit evidence.

Path rules are hints. If the work is T4 by meaning, use a tracked task even when `check` did not flag it.

## What lean does not create

No task folders under `Docs/Work`, STATE, fingerprints, approval receipts, resume notes, execution notes or cleanup logs. The feature backlog `Docs/Work/FEATURES.json` is the only lean file there. Planning questions are asked in the conversation; the resulting decisions go into the commit message.

## Failures

Diagnose and fix the cause before the next check; `repeat` and `same_failure` show when a run repeated a known failure. If the cause is outside the project, such as a missing local service, report the blocker in one line and continue other features. A feature whose checks cannot pass is not committed as done.
