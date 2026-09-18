# Frontend Runbook

For frontend changes:

Read [BOUNDARIES.md](BOUNDARIES.md) and identify the changed component's runtime,
shared dependencies and API contract consumers. Do not import server internals,
DB clients or private credentials into browser code. Validate real connected flows,
not only mocked responses, before declaring an integrated feature complete.

1. Identify routes, states, responsive breakpoints, accessibility requirements, and backend contracts.
2. Baseline affected lint/type/unit/browser/build checks.
3. Verify loading, empty, error, success, keyboard, and permission-denied states as applicable.
4. Run the required Task/Phase browser interaction checks in scoped projects, or Full in legacy projects; run project-wide Full when expanded or explicitly required.
5. Capture desktop and mobile screenshots under the run evidence directory.
6. Record console errors, failed requests, and visual exceptions.

UI-only authorization is never sufficient. Sensitive action denial must be tested at the server boundary.

For a new connected feature, define the API contract first and use an explicit
[implementation group](IMPLEMENTATION_GROUPS.md) when backend and frontend code
must both exist for member completion tests. The sequence is all Baselines/entry
gates, backend implementation, frontend implementation, member verification/review,
then Phase verification/review. Keep loading/error/denied and real connection tests.

### Playwright evidence adapter

The browser check receives `PIPELINE_EVIDENCE_DIR`. A Playwright test should capture actual pages at the configured viewports and write `screenshots/manifest.json`, for example:

```javascript
const root = process.env.PIPELINE_EVIDENCE_DIR;
const shots = [];
for (const item of [{kind:'desktop',width:1440,height:900},{kind:'mobile',width:390,height:844}]) {
  await page.setViewportSize({width:item.width,height:item.height});
  await page.goto('http://127.0.0.1:4173/');
  const path = `screenshots/home-${item.kind}.png`;
  await page.screenshot({path: `${root}/${path}`, fullPage:false});
  shots.push({...item,path,url:page.url()});
}
require('fs').writeFileSync(`${root}/screenshots/manifest.json`, JSON.stringify(shots));
```

This is an adapter pattern, not supplied evidence: the configured test must start a real non-production server, assert interactions, and produce decoded images at the declared dimensions.
