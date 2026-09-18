# Adopt without overwriting

1. Confirm the target repository and user's adoption intent. Read existing AGENTS.md, Git status and build/test configuration. Installing this plugin alone is not adoption of the current repository.
2. Run the wrapper's `doctor`. Missing Python packages can be installed into a project/tool-specific virtual environment using the bundled requirements, when within the requested setup. Do not download another engine or silently execute installers during a read-only audit.
3. Inspect `assets/pipeline/README.md`, `Docs/Runbooks/CONFIGURATION.md`, and `Docs/Governance/ENFORCEMENT.md` under the bundled pipeline. These are maintained engine documentation, not duplicate skill policy.
4. Run `adopt --target <absolute target>` only for an authorized adoption. It refuses conflicting files and symlink destinations. An existing README/AGENTS/requirements file is a conflict too: never remove it to make installation work. Instead adopt into an isolated new staging directory, compare the generated files with the target, and propose or perform an explicitly scoped integration preserving the user's content. Do not run staged commands as if the target were configured. When a conflict requires choosing a new governance policy, ask the user.
5. Configure the installed project's six source documents, supported domains, proven argv commands, path rules and Git comparison base. New adoption uses `approval_policy: standard`; do not ask for human identity or external trust in standard. T3/protected decisions use explicit user receipts, not AI approval. Provision trust only when a signed gate is actually required. The copied configuration deliberately has `mode: project` and `ready: false`. Do not enable readiness merely to silence an error. Never use a dummy passing command to stand in for real tests.
6. Follow the configuration runbook's bootstrap sequence: create the DRAFT task, establish real command coverage, set readiness only when configured, and validate. Preserve the distinction between project readiness and task READY. Explain that strict signing-key custody, protected CI and evidence-producing jobs still require organization setup.

An existing v1 or otherwise incompatible pipeline needs an explicit migration plan, not overwrite or silent reinterpretation. Read the target migration documentation and compare versions. Plugin updates never automatically upgrade an adopted project's engine, config or approved task records.

With engine 2.7, first run `inspect --target <project>` and
`adopt --target <project> --preview` (read-only). For an explicitly requested
compatible 2.6+ update, read bundled `Docs/Runbooks/UPDATES.md`: `upgrade --target`
defaults to preview; `--apply` preserves user-owned files and backs up managed
engine bytes. A legacy installation requires its known original `--baseline`,
never hashes guessed from the current project. Restore uses the returned explicit
transaction ID. No automatic dependency install, approval, budget reset or
project readiness follows from these commands.

For engine 2.6 web adoption, read `Docs/Runbooks/BOUNDARIES.md` before configuration.
Inspect actual entry points and runtime paths, declare allowed dependencies and
real contract provider/consumer/compatibility/integration checks, and exercise the
chosen adapter on a forbidden import as well as a permitted one. Preserve logical
trust boundaries without requiring separate repositories or a fictitious backend.
Legacy NOT_CONFIGURED remains visible and cannot be reported as boundary PASS.

## First feature before expansion

When adoption includes project implementation, execute these stages in order.
An adoption-only request ends after configuration with its actual evidence and
remaining implementation work reported; it does not authorize a new feature.

1. **Map the repository and stacks.** Inspect or establish the user's selected
   layout. For a new single-repository backend/frontend project, use `backend/`
   and `frontend/` unless the user or framework specifies another layout; different
   stacks do not require different repositories. Record each runtime's source roots,
   stack, working directory, allowed imports, API contract and verification scope
   in project-owned configuration and architecture documents. Keep DB clients and
   credentials server-side. Exit only when actual components and contract parties
   are mapped without orphan or overlapping paths. Do not add a backend or DB to
   a project that does not need one.
2. **Connect executable checks.** Follow the bootstrap sequence above and the
   configuration runbook. For an empty repository, establish only the minimal
   runnable scaffold and real test harness needed for the authorized setup before
   business-feature implementation. Execute any available pre-change Baseline
   before scaffold edits; if none exists, record NOT_RUN and the reason, never PASS.
   Demonstrate each required command from its declared cwd: applicable build,
   lint/typecheck, unit, contract provider/consumer/compatibility, DB integration,
   browser interactions and boundary graph checks. Exercise permitted and forbidden
   imports with a stack-appropriate adapter. Retain real logs/results; zero tests,
   dummy success commands and disabled required checks do not establish coverage.
   Once configured, create the intended DRAFT tasks, validate project readiness,
   prepare their final documents and capture actual Baselines before implementing
   the feature. An existing executed domain failure retains FAIL under the Baseline
   policy; missing or unexecutable checks must be fixed before task entry. Project
   configuration readiness alone does not prove that the feature works.
3. **Validate one complete feature.** Select a small feature already in the user's
   requested scope that crosses the actual application boundaries. Define observable
   acceptance criteria for UI interaction, API response, persistence and applicable
   error paths; omit absent layers with a reason. A small connected feature may be one task across layers. When intentionally
   split members require each other before verification, use prepared member tasks
   and a Phase with an explicit implementation group: external prerequisites -> all member Baselines/entry gates -> backend
   implementation (including persistence when needed) -> frontend implementation
   -> unchanged member Fast/Task/review gates -> Phase integration/E2E and review.
   Keep real client/server/storage interactions in the evidence; mocks alone do
   not prove the connection. Capture desktop/mobile browser evidence when required.
   Exit only when the task, or every member plus its Phase, is validly DONE through
   engine gates with acceptance evidence and required approvals. A successful
   build, doctor, configuration validation or implementation acknowledgement is
   insufficient. STATE.md remains the sole owner of task status.
4. **Expand within the authorized scope.** Keep the initial implementation queue
   limited to the first feature, its Phase and required prerequisites. After its
   completion gate passes, continue the remaining requested work in the existing
   checkout. If later feature tasks are already in the same plan, give each an
   explicit completion dependency on the first feature's Phase (or its task for
   a single-component feature). Do not leave them independently runnable while
   the first feature is blocked. Retain evidence links in task plans/verification;
   do not create another readiness flag. Continue ordinary work without a new
   permission question; preserve existing protected/release boundaries. Resolve
   failed gates, stale evidence or unfinished integration before expansion.

For resume or an already adopted project, inspect its configuration, task STATEs,
retained verification and review evidence first. Reuse valid evidence for the same
stack and boundaries; an unrelated feature does not restart this sequence. If the
setup or integrated-flow proof is missing or invalidated, complete the missing
stage within the authorized work before bulk implementation. Report an external
blocker explicitly rather than declaring readiness from plugin installation.

## Bound setup to the product

Reuse existing substantive documents for the six source roles (roles may share a file), existing commands and valid evidence. Choose actual domains; the full kit catalog is not a backlog. Do not build generic adapters, CI services or pipeline tooling before a requested feature unless a demonstrated blocker requires them. Adoption alone does not authorize a demonstration feature.
