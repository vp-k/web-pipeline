# Deliver the requested product

The pipeline records and verifies product work; it is not a second product to
build during ordinary development. If implementation is requested, the first
milestone is one real requested feature with observable acceptance evidence.
Adoption alone does not authorize an invented demonstration feature.

1. Inspect existing entry points, package scripts, tests and requirements. Reuse
   the repository's layout and proven checks rather than introducing a framework.
2. Select actual supported domains explicitly during adoption. The kit's complete
   domain vocabulary is an example configuration, not a backlog. Include real
   security, data and API responsibilities; do not add payment, hosting or deployment
   to a project that does not need them. Never disable existing required checks.
3. The six `sources` are information roles, not six new writing assignments. Point
   them to existing substantive documents; several roles may share one document.
   Keep task planning concise and source-backed. Do not invent six questions just
   because CLARIFICATIONS has six analysis areas.
4. Release-only setup does not block development readiness; those checks still
   must execute when Release is requested. Wire existing argv commands and add missing checks needed for the actual first
   feature. Do not build a generic adapter library, dashboard, CI service or plugin
   as a prerequisite unless explicitly requested or a demonstrated blocker requires it.
5. A small connected feature may be one task spanning frontend, backend and data.
   Split only for meaningful independently reviewable units. Use implementation
   groups when already split members need each other's code before their tests pass.
   Preserve every applicable acceptance, domain and integration check either way.
6. Once readiness and task entry gates pass, implement the feature immediately.
   Reuse valid evidence instead of repeating setup. Expand to remaining requested
   features after that feature passes its gates; do not restart adoption per task.
7. Report product behavior delivered and actual tests. If setup is still blocking,
   name the concrete feature/check it unblocks and the next product action.

A new empty repository needs minimal runnable scaffolding and genuine checks.
An existing repository does not need that scaffolding rebuilt. Do not repair the
pipeline engine inside every product repository; diagnose a defect narrowly and
prefer a safe supported path. Engine upgrades remain explicitly scoped maintenance.
Infrastructure, Release and production remain outside ordinary development scope.
