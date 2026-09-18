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

## Planning records after an upgrade

Tasks created or explicitly revised by the current engine carry
`planning_version: 1` and a `CLARIFICATIONS.json` record. Existing unrevised tasks
keep working and report NOT_CONFIGURED planning coverage. Do not fabricate old
answers, set the marker by hand or revise active work as part of installation; adopt
the record at the next explicit revision. See [planning questions](CLARIFICATIONS.md).
