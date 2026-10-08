# Adoption and managed engine updates

Adoption and upgrades run from the installed plugin's wrapper, which verifies the
bundled kit before invoking the engine. Ordinary task commands always use the adopted
project's local engine (`python -m web_pipeline ...` from the project root).
Installing or reinstalling the plugin never upgrades an adopted project.

```console
python "${CLAUDE_PLUGIN_ROOT}/scripts/pipeline.py" doctor
python "${CLAUDE_PLUGIN_ROOT}/scripts/pipeline.py" inspect --target "<project>"
python "${CLAUDE_PLUGIN_ROOT}/scripts/pipeline.py" adopt --target "<project>" --preview
python "${CLAUDE_PLUGIN_ROOT}/scripts/pipeline.py" adopt --target "<project>" [--domains a,b] [--ci]
python "${CLAUDE_PLUGIN_ROOT}/scripts/pipeline.py" upgrade --target "<project>"
python "${CLAUDE_PLUGIN_ROOT}/scripts/pipeline.py" upgrade --target "<project>" --apply
python "${CLAUDE_PLUGIN_ROOT}/scripts/pipeline.py" restore --target "<project>" --transaction <id>
```

The plugin exposes these as `/web-pipeline:adopt` and `/web-pipeline:upgrade`.
`doctor`, `inspect` and `--preview` perform no writes and do not prove readiness.

## Adoption

`adopt` (engine command `init`) copies the pipeline into a project without overwriting anything:

- The engine folders `web_pipeline/`, `Schemas/`, `Scripts/` and the files
  `pipeline.config.yaml`, `PIPELINE.md`, `requirements-pipeline.txt` must not already
  exist; any conflict aborts before the first write. An already adopted project
  (`.pipeline-install.json` present) uses `upgrade` instead.
- `Docs/Governance`, `Docs/Runbooks`, `Docs/Product`, `Docs/Architecture`, `Docs/ADR`
  and `Templates/` files are copied only where absent; existing files are reported as
  `preserved` and left byte-for-byte unchanged.
- `CLAUDE.md` gets an `@PIPELINE.md` import appended (the file is created if missing);
  existing content stays first and untouched. `.gitignore` gets only the pipeline
  lines it lacks appended; it is never rewritten.
- README, tests and examples are never copied. `--ci` opts in to
  `.github/workflows/project-policy.yml`. `--domains a,b` sets
  `project.supported_domains`; unknown names abort.
- The copied config is written with `project.mode: "project"` and
  `project.ready: false`. Symlinked or junctioned destinations are refused.

Adoption records `.pipeline-install.json`: a hash inventory of the managed files it
installed, not a human identity, trust file or approval. Track it in Git. Then follow
[CONFIGURATION.md](CONFIGURATION.md); no framework configuration is guessed and
dependencies are never installed by maintenance (`requirements-pipeline.txt` lists them).

## Upgrade

`upgrade` compares the project's managed files against its install receipt and the
new bundle. A legacy installation without a receipt needs
`--baseline <known-original-engine-directory>` for both preview and apply. Obtain
that exact installed release from a known source; never generate a baseline by
copying the current, possibly edited, target. Only compatible schema-2 engines from
2.6 onward are supported; no downgrade, implicit migration or reset.

Apply rewrites only `web_pipeline/`, `Schemas/` and receipt-listed files under
`Scripts/`:

- Any added, edited or missing file under `web_pipeline/` or `Schemas/` blocks the
  upgrade until the user decides how to resolve it; maintenance never overwrites an
  edit silently.
- Files a project adds under `Scripts/` (absent from the install receipt) are
  project-owned: preserved through upgrade and restore and reported as
  `project_owned`. A project-owned file whose path collides with a new engine file
  blocks the upgrade; rename it first.
- `pipeline.config.yaml`, `requirements-pipeline.txt`, `PIPELINE.md`, `CLAUDE.md`,
  `Docs/`, `Templates/`, CI files, product code, approvals, task states, budgets and
  evidence are not touched. Compare the new kit's runbooks, templates, dependencies
  and CI separately and integrate only an explicitly scoped change. New engine
  options (for example structured test results or `respect_gitignore`) are not
  enabled in an existing configuration automatically.

Stop pipeline operations and external editors before applying. Apply takes the
`upgrade` lock, refuses to run while any other lock is held (stale locks whose
process is gone are cleared first), rechecks current hashes, and records a
transaction with backups under `.pipeline-upgrades/<id>/` before the first engine
write. Keep that directory out of Git and do not remove it until recovery is no
longer needed. An interrupted transaction must be restored before another upgrade.
`restore` validates backups and refuses when managed files were edited after the
upgrade; it never erases those edits to force recovery, and it can resume an
interrupted restore. These are local integrity checks, not protection against an
attacker who can rewrite the engine, receipts and backups.

After apply, run `python -m web_pipeline validate` and fresh verification.
Maintenance does not grant READY/DONE, renew approval, recapture Baseline or refund
iteration budgets. The changed source tree invalidates current-code evidence;
existing task workflows may require explicit revision/re-verification. A rollback
restores engine bytes, not application data or deployment state.

## Moving an existing project to lean

An upgrade does not change `pipeline.config.yaml` or `Docs/`. A project adopted before
2.14 has no `workflow` key, so it stays `tracked`. A project adopted before 2.15 keeps
its old path rules. With the user's agreement:

1. Copy `Docs/Runbooks/LEAN.md` from the new kit and set `"workflow": "lean"`.
2. Compare `risk.path_rules` with the new kit's `pipeline.config.yaml`. Adding a
   shipped rule only promotes.
3. Replacing an old broad glob such as `*auth*` with the word rules removes a rule.
   Show the difference and let the user decide.

## Upgrading to 2.16

- Task fingerprints became version 2. Tasks prepared before 2.16 keep version 1
  and reach DONE without a completion seal, so they keep the earlier
  current-source validation. Their next explicit revision moves them to version 2.
  Do not revise active work only to switch.
- New adoption merges line-ending rules into `.gitattributes`. An upgrade does not
  edit `.gitattributes`; with the user's agreement, append the lines of the kit's
  `gitattributes.txt` that are missing.
- Lean projects can keep a feature backlog and run a scoped Task check; copy the
  new `Docs/Runbooks/LEAN.md`. `verification.scopes` in a lean project may leave
  `Phase` checks empty.

## Upgrading to 2.17

Upgrade the engine first, then copy the documents below from the new kit, then run
`validate`.

- `Docs/Runbooks/LEAN.md` is now the only source of the lean rules and explains the
  check output: `repeat`, `same_failure`, `test_changes`, `base_commit`, `warnings`,
  `last_check` and `commit_gate`. Copy it from the new kit.
- In `PIPELINE.md`, replace the `lean` bullet under Workflow mode and the Work rhythm
  section with the kit's lines. The rhythm now states the tracked `repeat` input and
  the failed-attempt rule.
- Copy `Docs/Runbooks/CONTINUATION.md`, `Docs/Runbooks/CONTINUOUS.md`,
  `Docs/Runbooks/VERIFICATION_SCOPES.md`, `Docs/Governance/VERIFICATION_POLICY.md`,
  `Docs/Governance/00_OPERATING_MODEL.md` and `Templates/ITERATION_TEMPLATE.md` for
  the same wording.
- A lean check whose command declares a `test_report` now fails when the report is
  missing, invalid or below its own limits. Fix a command that does not write its
  declared report; removing the report is a weakened check and needs the user.
- A lean check now records a digest of the whole `pipeline.config.yaml`. A check
  recorded before the upgrade is never `current`, so `feature done` refuses it: run
  check once more before finishing a feature.
- The tracked failed-attempt count now counts failures since the last covering PASS.
  A count recorded before the upgrade has no failing profile, so the task's next PASS
  of any profile clears it. Older accounting that `loop renew --task` migrates takes
  its failing profile from the retained runs instead, or `Full` when none survived.
- Tracked runs now report `repeat` against the task's previous run of the same
  profile, comparing its checks, task revision and approved exceptions as well. The
  first run of each profile after the upgrade never reports one.
- A tracked PASS ends a same-failure sequence only when its profile is at least as
  wide as the runs that failed. A sequence recorded before the upgrade has no profile,
  so the next PASS of any profile ends it.
- An interrupted tracked run that left no summary keeps its failure at the profile it
  was reserved for. A reservation made before the upgrade counts as `Full`.
- `outside_scope` no longer lists paths of components that depend on a declared one.
- A user-requested `loop renew --task` releases a same-failure or external-retry stop
  the task reached and records the released counts in the grant. It needs no extra
  budget for that. A count below its stop is kept, so a task stopped before the
  upgrade resumes only after such a renewal.
- External retries count blockers in a row: a run with no external blocker whose
  commands started ends the count. A count recorded before the upgrade stays until
  such a run.
- A feature that is already `ACTIVE` has no `base_commit` and keeps comparing with
  `HEAD`. A feature started with `feature next` after the upgrade records it.

## Planning records after an upgrade

Tasks created or explicitly revised by the current engine carry
`planning_version: 1` and a `CLARIFICATIONS.json` record. Existing unrevised tasks
keep working and report NOT_CONFIGURED planning coverage. Do not fabricate old
answers, set the marker by hand or revise active work as part of installation; adopt
the record at the next explicit revision. See [planning questions](CLARIFICATIONS.md).
