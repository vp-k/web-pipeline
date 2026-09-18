# Frontend/backend boundary configuration

Separate responsibilities and runtime privileges, not necessarily repositories,
processes, teams or agents. A static site needs no invented backend. A full-stack
framework can stay in one repository, but browser, server and shared modules must
still have explicit ownership. Read this runbook for frontend/backend/API work and
when configuring or changing architecture boundaries.

## Responsibilities

| Runtime | Owns | Must not own |
|---|---|---|
| browser | Presentation, interactions, local view state | Secrets, DB access, authoritative authorization or payment decisions |
| server | Input validation, authorization, business rules, persistence/integrations | Importing browser implementation as ordinary server dependencies |
| shared | Runtime-neutral schemas, DTOs, pure utilities | Server internals, browser globals, secrets or environment-specific side effects |

Browser-to-server calls cross an API contract; they are **not** permitted source
imports. Database clients and private SDKs stay server-side. Server validation and
authorization remain mandatory even when the UI validates inputs or hides controls.

## Declare actual paths

`pipeline.config.yaml` accepts an optional `boundaries` block. New web adoption
must map the actual source layout before claiming boundary coverage. Existing
projects without it remain compatible but `validate` warns `NOT_CONFIGURED`; overall
policy PASS in that case does not prove import isolation. This distributable kit has
no application layout and intentionally does not invent one.

Merge the following example into a configured project, replacing paths, package
names and check IDs with real facts. It is not an executable default configuration:

```json
{
  "boundaries": {
    "source_patterns": ["src/*", "contracts/*"],
    "components": [
      {"id":"web", "runtime":"browser", "paths":["src/client/*"], "depends_on":["shared"]},
      {"id":"api", "runtime":"server", "paths":["src/server/*"], "depends_on":["shared"]},
      {"id":"shared", "runtime":"shared", "paths":["src/shared/*", "contracts/*"], "depends_on":[]}
    ],
    "dependency_check": "boundary-imports",
    "server_only_packages": ["private-db", "private-db/*"],
    "contracts": [{
      "id":"public-api", "paths":["contracts/api.json"],
      "provider":"api", "consumers":["web"],
      "checks": {
        "provider":"contract-provider", "consumer":"contract-consumer",
        "compatibility":"contract-compatibility", "integration":"integration"
      }
    }]
  }
}
```

Patterns are case-sensitive repository-relative `fnmatch` patterns; `*` spans `/`.
For example `src/client/*` includes nested files. They are not shell/tsconfig globs:
`src/**/*.ts` does not match `src/root.ts`. Use `/`, no absolute paths or `..`.
Inventory is the union of source patterns and component paths. Every inventoried
file needs exactly one component, every component needs files, and each contract
needs a file inside that inventory. Overlap, orphan files, empty inventories and
local imports into unscanned files fail. Cover all application entry points; a
source root omitted from both pattern sets cannot be discovered by this declaration.

Same-component imports are allowed. Cross-component imports require `depends_on`
and runtime compatibility: browser -> browser/shared, server -> server/shared,
shared -> shared. Permission cannot override the runtime restriction. Type-only
imports and reexports are included. Shared changes propagate classification to
declared transitive dependents; contract changes include both provider and consumers
and the API domain. Ordinary risk/path/protected rules continue to apply.
Add risk path rules for each actual public/webhook contract location; the generic
contract model does not infer whether an API is public or whether a diff is breaking.
Those protected decisions still need semantic classification and the existing gates.

Risk classification and verification use one impact closure: declared/changed
components, changed contract provider/consumers, then transitive dependents from
both the boundary and verification models. A dependent authorization component
therefore raises classification even when its dependency appears only in the
boundary model. Additional affected checks never justify leaving risk at T1.

For a static project declare only browser/shared components and `contracts: []`.
Do not create placeholder server files or dummy checks to satisfy the model.

## Execute and retain the dependency graph

Register a real non-mutating command, enabled in all five profiles:

```json
{
  "id":"boundary-imports", "enabled":true,
  "profiles":["Policy","Baseline","Fast","Full","Release"],
  "argv":["node","Scripts/boundary-graph.cjs","--tsconfig","tsconfig.json"],
  "cwd":".", "timeout_seconds":120,
  "artifacts":["artifacts/boundary-graph.json"], "environment":"test"
}
```

The supplied JS/TS adapter requires Node and the project's own TypeScript >=5 <7;
it does not install dependencies. Omit `--tsconfig` only when no custom resolution
is needed. It uses the compiler AST/resolver for imports, reexports, type imports,
literal dynamic imports and CommonJS require. JSON is parsed as data; JSON Schema
references are the contract checks' responsibility. Syntax errors, unresolved or
computed imports and unsupported file types fail. Known opaque loaders fail too;
arbitrary runtime code generation cannot be completely analyzed statically.

Vue SFCs, Go/PHP, virtual modules, bundler aliases/conditions, external workspace
symlinks, CSS/assets and framework bridges need a suitable compiler/bundler adapter.
Do not omit those source files or reclassify server modules as shared to obtain PASS.
Next.js server/client bridges need framework-aware checking; this generic adapter
does not interpret `use client`, server actions or exported package browser safety.
Use actual framework build, bundle/secret checks and security tests as well.

Before execution the engine writes `artifacts/boundary-input.json`: the complete
declared inventory of paths and SHA256 bytes, model digest and tree digest. The
adapter reads it from `PIPELINE_EVIDENCE_DIR` and emits this protocol:

```json
{
  "schema_version":"1.0",
  "files":{"src/client/main.ts":"<actual 64-character SHA256>"},
  "edges":[{"from":"src/client/main.ts", "external":"some-package"}],
  "unresolved":[]
}
```

Use `to` for resolved local repository-relative paths, or `external` for packages,
never both. Include all files and all resolved edges, including package root names
for aliased/subpath imports. Builtins normalize to `node:`. Browser/shared imports
of Node builtins or `server_only_packages` fail. The engine requires exact coverage
and hashes, applies policy itself, retains both artifacts, and revalidates them at
gates. A zero exit without a valid graph cannot PASS. The check runs even for Fast;
it is currently a full inventory scan, not an affected-file optimization.

A valid graph showing a preexisting forbidden edge may establish a **FAIL Baseline**
(adapter exit zero, engine semantic failure). It is historical evidence, not a
waiver for Full. Missing/corrupt graphs cannot establish that Baseline. Exceptions
use existing scoped approval gates and remain NOT_APPLICABLE, never executed PASS.

## Contract and end-to-end completion

Each declared API contract has one server provider and distinct consumers. Bind
provider, consumer, compatibility and integrated-flow checks to enabled command IDs
with both Full and Release profiles. One real suite may cover several roles; an
import graph cannot substitute for any of them. Legacy Full/Release execute all declared contract check IDs. In scoped projects,
Task/Phase include contracts touching any affected participant and all member checks;
project-wide Full/Release still execute every declared contract. See VERIFICATION_SCOPES.md.
Actual declared contract bytes participate in the source revision fingerprint.

For a new provider and consumer that must both exist before these completion checks
can pass, use [implementation groups](IMPLEMENTATION_GROUPS.md). The enforced order
is all member Baselines/entry gates, ordered implementations, unchanged member
verification/review, and then Phase verification/review. Contract checks are retained.

Configure provider response/schema validation, consumer decoding/error handling,
breaking-change comparison, and a real non-production UI/client-to-server flow.
Mocks remain useful unit/consumer evidence but are not the sole evidence of a
connected feature working. Link these checks to acceptance criteria, including
error/denied cases, and keep browser/screenshot requirements where applicable.

Changing policy, contracts or approved scope requires the existing revision and
renewed-evidence process; never silently migrate an adopted project's configuration.
Protect adapters, configuration and CI ownership. Inventory hashes detect stale or
missing files, not deliberately omitted edges from a dishonest adapter. Boundary
checks supplement test review and external permissions; they are not a security
sandbox or proof that an npm dependency is browser-safe.
