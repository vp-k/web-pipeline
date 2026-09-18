# Frontend/backend boundaries — 2.6 implementation plan

User scope: enforce logical web boundaries without requiring separate repositories,
services or agents. Existing approval and production boundaries remain unchanged.

1. Capture the unchanged engine regression Baseline.
2. Add optional explicit source coverage, browser/server/shared components and
   permitted dependencies. Legacy absence remains visible as NOT_CONFIGURED, not
   a claim of boundary validation. No silent project configuration migration.
3. Execute a dependency adapter and independently check its source coverage and
   resolved graph against the declared boundary policy. Retain both input inventory
   and output graph as hash-bound run evidence, and revalidate them at gates.
4. Provide an AST-based JS/TS adapter using project TypeScript (supported compiler
   API <7). Unsupported files, unresolved/computed imports and opaque loaders must
   fail, not be silently omitted. Other stacks need a compiler/bundler adapter.
5. Bind declared contracts to provider/consumers and their actual verification
   commands. Full/Release conservatively run all configured contract provider,
   consumer, compatibility and integrated-flow checks. Static-only projects can
   declare no contracts/server; no mock-only completion for a connected feature.
6. Exercise passing and failing real fixtures, run complete regressions, rebuild
   the standalone distribution, and update the existing personal plugin.

## Deliberate limits

- Graph provenance is only as trustworthy as its configured adapter/CI. Coverage
  checks catch missing files, not malicious omission of an edge by a compromised
  adapter. Review/protect the adapter and require application build/security tests.
- Runtime rules are conservative: browser and shared modules cannot import server
  internals; server cannot import browser implementation. Framework-specific
  server/client bridges require a framework-aware adapter, not blanket exceptions.
- Component and package restrictions supplement, not replace, server authorization,
  secret scanning, database permissions or production credentials isolation.
- No regex-only import parser is presented as full JavaScript/TypeScript analysis.
- Existing projects remain on their own engine/config until explicitly upgraded.
  No external application state, user approvals, budgets, git commits or pushes are
  changed by this request.

## Evidence

- Pre-integration Baseline: 129 engine tests PASS, zero failures/errors/skips.
  `Reports/Pipeline/delivery-20260911T030521Z-4f3c6c8b/delivery-validation.json`.
- JS/TS AST/CLI: 9 PASS; actual adapter-to-engine integration: 2 PASS, zero skipped.
  `Reports/Pipeline/boundary-adapter-c0239ac2c4d5/boundary-validation.json`.
  The actual integration rejects forbidden imports despite parser exit zero and
  rejects unresolved imports as a Baseline. Separate Python protocol fixtures do
  not pretend to parse real JavaScript.
- Distribution regression: 6 PASS, zero failures/errors/skips.
  `Reports/Pipeline/packaging-9e6112c10467/packaging-validation.json`.
- All 15 boundary regressions also PASS when executed from the built bundle.
  Standalone and installed doctor validate 111 asset files; skill/plugin validators
  PASS. Final full engine regression: 144 PASS, zero failures/errors/skips.
  `Reports/Pipeline/delivery-20260911T033415Z-cccdc7fc/delivery-validation.json`;
  executed log SHA256
  `e6adcc4d026551f6de40eb4199f41d651df89f2e36f1650b78529ceed10264c1`.
  This final rerun includes malformed-JSON evidence handling and its regressions.
- Built `dist/package-2.6.0/`; plugin ZIP SHA256
  `df73ca658efabaf48d03373d56c879a141c88c77de534835009b89c02ce065cc`;
  standalone skill ZIP SHA256
  `a2c3e4750182ba95013e74846ec72a6ce3117374c456863465349d30eda3359c`.
- Refreshed the tracked standalone snapshot and reinstalled the existing personal
  plugin as `2.6.0+codex.20260911033627`. Marketplace entries and the unrelated app
  plugin were not changed. Existing project migration, new-thread discovery,
  remote CI and production operations are NOT_RUN. No commit or push performed.

Compiler adapter design reference:
[TypeScript compiler API](https://github.com/microsoft/TypeScript/wiki/Using-the-Compiler-API).
