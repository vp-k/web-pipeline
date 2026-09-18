# Real local web lifecycle

This plain-JavaScript reference uses a real loopback Node HTTP server, a SQLite
file database and Chromium. It is not a Next/Vue adapter or a production starter.
Fixed `demo-reader-only` / `demo-writer-only` tokens are fictional fixtures, not
credentials or a usable authentication design. The server requires explicit demo
mode and binds only to `127.0.0.1`. Never publish it or use production data.

Prerequisites: Python 3.11+ with the root requirements, Git, Node 22.15+ (native
`node:sqlite`; experimental on 22.15), scoped Node dependencies and Chromium:

```console
npm ci --prefix Packaging/node-tools --ignore-scripts --no-audit --no-fund
node Packaging/node-tools/node_modules/@playwright/test/cli.js install chromium
python examples/web/run_pipeline.py --node-tools Packaging/node-tools/node_modules
```

The example runner does not install packages or browsers. `--browsers <directory>`
selects an existing isolated browser cache. Linux may require Playwright's explicit
`install --with-deps chromium` setup. A distributed skill does not include the
maintainer's Node-tools directory: use an existing scoped directory containing
`@playwright/test` 1.63.0 and `typescript` 5.9.3 and pass it to `--node-tools`.

The runner creates an isolated temporary project, captures Baseline, introduces a
real forbidden browser-to-server import, checks that it fails, repairs it while
changing the heading, pauses/resumes the task, runs Full, records an explicitly
local self-review and executes the DONE/merge gates. It does not manufacture an
independent reviewer or human approval. The scoped T2 task changes only the UI;
the role and database behavior are preexisting baseline fixtures.

Six executed tests cover provider responses, consumer rejection of malformed
responses, frozen v1 compatibility, denied authentication/role/origin/input
requests, persistence after server restart and desktop/mobile browser interaction.
This is a small custom contract, not an OpenAPI-compliance claim. The native server
runs in a separate process from the browser test runner. Browser screenshots,
server/test logs, structured case results and original pipeline evidence are kept
under `Reports/Pipeline/web-example-<id>/`; failed runs remain there too. The copied
task's `STATE.md` is the only workflow-state record. No production deployment occurs.
