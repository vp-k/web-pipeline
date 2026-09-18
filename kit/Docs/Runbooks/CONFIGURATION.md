# Project configuration

`pipeline.config.yaml` uses JSON syntax, a strict subset of YAML 1.2. The engine parses JSON and does not accept general YAML features. Every JSON or text file the engine reads (config, STATE blocks, task records, plans, receipts, locks) tolerates a UTF-8 BOM, so files written by PowerShell load unchanged.

An adopted project starts with `project.mode: "project"` and `project.ready: false`. Before readiness, set all six `sources` to existing repository-relative documents, declare supported domains, configure risk/path coverage, and register proven commands as argv arrays. Each command has `id`, `enabled`, `profiles`, `argv`, `cwd`, `timeout_seconds`, `artifacts`, and a non-production `environment`. Shell strings and compound interpreters (`sh -c`, `cmd /c`, PowerShell `-Command`) are rejected.

Requirements name command IDs by domain and profile. Development readiness requires enabled Policy/Baseline/Fast/Full checks for supported domains. Release-only definitions may remain disabled until Release is requested; the Release runner reports them NOT_RUN and cannot grant readiness. Release inherits Full. A missing or disabled requirement is NOT_RUN and fails the profile. Production commands are forbidden: Release establishes readiness only.

## Approval policy

New adoption sets `approval_policy: "standard"`:

- Unprotected T0–T2 has no user-approval gate and needs no human identity or trust configuration. T1/T2 completion records a local self-review (`review --task ... --decision ...` in REVIEW state, or the loop's `reviewed` outcome); T0 needs no review record.
- Protected changes, T3/T4, check exceptions and T4 Release readiness use scoped user receipts: `approval-request` shows the exact decision, `approve` records the user's answer. Receipts do not prove human identity or independent review; see [APPROVALS.md](APPROVALS.md).

`strict` requires Ed25519-signed records for every human gate (Reviewer for T1+, Tech Owner design approval for unprotected T2, domain owners for protected work, two distinct signers for T4 release) and an external trust file supplied with `--trust` or `WEB_PIPELINE_TRUST`. Omitting the field means strict. The trust file maps human identifiers (not necessarily real names) to roles and Ed25519 public keys, never private keys. Protect it with external access controls and keep signing keys unavailable to AI: an outside-project path alone is not a security boundary. Repository write access, hashes, and CI logs do not establish human authority.

Standard receipts never need a trust file; only existing signed records do. Changing policy is an explicit governed config change, not an automatic plugin upgrade; it invalidates prepared fingerprints, so revise prepared tasks.

## Bootstrap checklist

1. Confirm Git history and the intended comparison base ref.
2. Establish source documents and current content.
3. Register commands already demonstrated from their declared working directories.
4. Configure path rules and every supported-domain requirement.
   For web adoption, also read [BOUNDARIES.md](BOUNDARIES.md), map actual runtime
   components/source roots and register the dependency and contract adapters.
   Legacy absence warns NOT_CONFIGURED and does not prove import isolation.
5. Keep hosting/environment enforcement separate. Provision trust only for strict signed gates; standard work starts without it.
6. Create the intended DRAFT task with `new --task ... --domains ... --base-ref ...`. Progress validation permits an empty active task set with a warning; only the merge gate rejects it. Do not invent a setup task merely to run configuration validation.
7. Set `ready: true`, then run `python -m web_pipeline validate`. If it fails, return readiness to false while correcting configuration; kit mode is not a project bypass. Populate task documents, prepare, and capture Baseline before entering READY.

`python -m web_pipeline status` is the read-only orientation command: it reports adoption, engine version, readiness, policy, enabled checks, every task's status/tier/revision/iteration, held locks with owner liveness, the queue and a `next` hint. It never raises for an unadopted or not-ready project.

## Source fingerprints and exclusions

`project.generated_paths` may list only untracked build/test outputs such as `dist` or `coverage`. It cannot overlap governance, source, engine, schema, script, or template inputs. If Git tracks any file below an excluded path, snapshot validation rejects the exclusion; generated paths cannot hide tracked changes from classification or evidence binding.

`project.respect_gitignore` (boolean, shipped `true`) additionally excludes git-ignored *untracked* files from source fingerprints and tree digests, so build caches such as `.turbo/` or `*.tsbuildinfo` do not invalidate evidence. Tracked files are never hidden by an ignore rule. This requires Git; outside a repository it has no effect, and a ready project must have Git history anyway.

The same checks apply to `report_root` and implicit cache exclusions (`.git`, `node_modules`, `__pycache__`, `.venv`, `.pipeline-locks`, `.pipeline-upgrades`). Only `.gitkeep` markers may be tracked inside excluded outputs. Report paths cannot overlap Docs, Scripts, schemas, engine, CI, or source documents. Verify and revalidate the same checkout bytes; line-ending changes also invalidate content fingerprints.

## Path rules

`risk.path_rules` classify changed paths into domains, protected changes and a tier floor. Patterns are case-sensitive `fnmatch` patterns matched against POSIX-style repository-relative paths, and `*` also matches `/` (`Scripts/*` covers nested files; `*.sql` matches any depth). They only promote classification; semantic review still decides whether a diff is breaking or public.

The shipped rules treat dependency manifests and lockfiles as `major_framework_sdk` (security domain, T3): `*.lock`, `*-lock.json`, `*-lock.yaml`, `*.lockb`, `*npm-shrinkwrap.json`, `*go.sum`, `*go.mod`, `*package.json` and `requirements*.txt`. `*auth*`, `*session*`, `*payment*`, `*wallet*`, `*migration*`, `*.sql`, `*openapi*`, `*.graphql`, `*.proto`, `*webhook*`, `*.tf`, `.github/workflows/*`, `*Dockerfile*`, `*.env*`, `*secret*`, `pipeline.config.yaml`, `web_pipeline/*` and `Scripts/*` map to their protected changes. Add rules for each real contract, migration and infrastructure location in the project.

## Locks

Mutating commands take a lock in `.pipeline-locks/<name>.lock` recording the owner pid and start time. `python -m web_pipeline locks` lists them with `alive`; `locks --clear-stale` removes those whose process is provably gone. A stale lock is also reclaimed automatically by the next operation that needs it. A lock whose owner is alive, or whose file cannot be read, still blocks; never delete such a lock by hand.

## Verification scopes and planning

Structured planning is mandatory for new tasks and for tasks explicitly revised: `new` generates `CLARIFICATIONS.json` and `prepare` refuses unresolved material questions. This needs no policy change or configuration switch. Unrevised older tasks report NOT_CONFIGURED planning coverage. See [planning questions and source records](CLARIFICATIONS.md).

Configure real component paths, transitive consumers and separate executable suites
through `verification.scopes`; see [Task/Phase/Release configuration](VERIFICATION_SCOPES.md).
Task completion can then execute impacted acceptance/regression, Phase executes the
combined group, and Full/Release remain project-wide. Missing configuration keeps
legacy Full completion. Upgrade and scope adoption are separate explicit changes; revise
prepared tasks instead of reusing stale approvals or Baselines.

## Command adapter examples

Commands are argv arrays resolved through `PATH`/`PATHEXT` before execution, without a shell. `["npm", "run", "test"]`, `["pnpm", "test"]` and `["npx", "playwright", "test"]` therefore work on Linux, macOS and Windows alike; on Windows the `.cmd` shims are found automatically, so `npm.cmd` is unnecessary. Never wrap a command in `cmd /c` or `sh -c`.

Verification commands must be non-mutating: use formatter check modes such as `prettier --check`, and lint without `--fix`. Apply formatting or fixes during implementation, then rerun verification. If a command changes a governed source, task document, config, engine, or script while verification is running, source-stability validation rejects the run even if the process exited zero.

Go and PHP examples are `["go", "test", "./..."]` and `["php", "vendor/bin/phpunit", "--testsuite", "integration"]`. Set `cwd` to the relevant package/service root. Pipes, redirects, variable expansion, and chained commands belong in a reviewed dedicated script. POSIX shell hosts accept `sh verify.sh`/`bash verify.sh`, not `-c`/`-lc` or stdin forms; PowerShell requires explicit `-File`. Script authors must propagate failures faithfully. The shipped PowerShell adapters resolve their own engine location and support invocation from another working directory.

Checks receive `PIPELINE_EVIDENCE_DIR`, `PIPELINE_CHECK_ID`, `PIPELINE_TASK_ID` and `PIPELINE_PROFILE`; `WEB_PIPELINE_TRUST` is removed from their environment. A check must finish its descendants: the engine terminates the process tree on timeout and fails a command that abandons a running child even when the parent exited zero.

For legacy installations, follow [the explicit migration procedure](../Governance/MIGRATION_V1_TO_V2.md).

## Scope setup to the product

Read [PRODUCT_FIRST.md](PRODUCT_FIRST.md). Select actual supported domains rather than configuring the kit's whole example catalog. Reuse existing source documents and check commands. Six source roles may reference fewer substantive files; no engine gate requires six new documents. Readiness still requires all applicable checks, not dummy commands or disabled requirements. Once entry gates pass, proceed to the requested feature.

New adoption uses advisory cumulative time (`iteration_limits.time_budget_mode: "warn"`). Choose `enforce` for a requested hard time cap. Existing absent-mode configs and queues retain enforce; config changes invalidate fingerprints and require normal revision, not manual STATE edits.
