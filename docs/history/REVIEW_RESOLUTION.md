# Review resolution and acceptance evidence

This is the implementation's review trace, not a human approval or task workflow state. Run `python tests/verify_delivery.py` to generate the executed regression report under Reports/Pipeline.

Latest v2.1 local evidence: [69 tests PASS, zero failures/errors/skips](Reports/Pipeline/delivery-20260909T032900Z-8d272285/delivery-validation.json), [test log](Reports/Pipeline/delivery-20260909T032900Z-8d272285/unittest.log). Historical v2 evidence: [51 tests PASS](Reports/Pipeline/delivery-20260908T235223Z-766e485b/delivery-validation.json). The signed decisions in tests use ephemeral fixture keys; they are not production or human approvals.

## Full-review remediation (v2.1)

The eleven reproduced findings were fixed with 18 additional tests in `tests/test_review_regressions.py`. The pre-change baseline also passed its existing 51 tests, demonstrating that those checks did not cover these defects.

| Reproduced finding | Correction and regression evidence |
|---|---|
| DRAFT accepted by a CI readiness check | Separate progress/merge gates; merge rejects incomplete tasks, empty scope, kit and single-task filtering; PR job invokes merge |
| report_root hides tracked source | Validate output/governance overlaps and tracked files across report, generated and implicit cache exclusions |
| Baseline replaced after implementation or DONE | Baseline restricted to DRAFT; rejection preserves state |
| Valid N/A counted as recurring failure | Exclude authorized NOT_APPLICABLE from failure fingerprints; three successful Fast runs do not block Full |
| Acceptance checks missing from Full | Include task checks in Full/Release; prepare rejects checks that cannot execute there |
| BLOCKED-to-DRAFT bypasses revision | Require revise and an incremented revision; keep cumulative iteration budgets |
| Duplicate run ID destroys previous state | Reserve a unique run before changing counters or evidence pointers; compare the entire state after rejection |
| Policy profile bypasses actual policy | Invoke the common validator; stale classification cannot produce Policy PASS |
| Shell suffix/combined-flag bypass | Normalize shell host names and require explicit script operands; reject .exe and -lc/-c command forms |
| PowerShell caller-directory dependency | Resolve roots and execute from the adapter's engine directory; actual external-directory validation and installation tests |
| Dirty source lost during archive | Store exact verified bytes and manifest bound to Full tree digest; detect bundle tampering; refuse potential credential files before writing |

CI context tests also cover numeric artifact references, missing evidence and project-to-kit downgrades. Local module compilation and kit validation passed. The minimal installed example executed Baseline/Full and reached REVIEW; evidence is retained at `E:/code/web-pipeline-example-evidence-20260909-v21`. It is not a real web-stack integration result. Remote GitHub Actions was not executed.

## Original v2 findings

| Review finding | Implementation | Verification |
|---|---|---|
| PASS flags can create DONE | transition reads actual Baseline/Full evidence; no PASS CLI parameters | test_lifecycle: fabricated DONE, missing Baseline, signed-review lifecycle |
| CI ignores tasks | strict all-task scan and explicit base-ref; orphan task directories fail | test_governance all-task scan; strict project workflow |
| Declared risk hides changes | committed/staged/unstaged/untracked/deleted path union; promotion closure | test_governance diff promotion and migration classification |
| DB Full profile impossible | every protected rule's required profile/check pair validated | test_common unreachable migration check |
| ADR/schema not enforced | v2 machine records and Draft 2020-12 schema validation | common schema rejection and governance document gates |
| Release before approval | DONE T4 + current Full + signed domain/Release approvals; no production execution | lifecycle early Release rejection and release-specific tests |
| Weak owner strings/conditions | external Ed25519 trust, exact roles, scoped dated records and condition hashes | governance signature/role/stale/self-review tests |
| Incomplete protected checks | all 20 protected rules carry domains, roles and checks | config completeness and kit validation |
| Retry/time limits do not run | reserved attempts, same-failure records, elapsed deadlines and child timeout | runner limit and real timeout tests |
| Compound command masks failure | argv process boundary, explicit script adapters, shell command-form rejection | real exit-code/spawn/timeout tests |
| Unapproved N/A | signed check-scoped exception validation | governance/runner exception regression |
| Revision strings do not bind sources | hash actual source/spec/AC/plan/release content; revision invalidates evidence and approvals | lifecycle edited scope and code tests |
| Evidence reuse/tampering | unique run directories, log/image/artifact hashes, signed Full summary digest | lifecycle duplicate run, tamper and rehash tests |
| Bootstrap false-ready | schema and supported profile command coverage; strict project readiness | common and CLI validation tests |
| Unsafe paths/writes | containment, symlink checks, atomic replace and task locks | common traversal/lock tests and adoption preflight |
| Poor deployment provenance | commit recorded, source tree digest and policy digest bound to run | run validation and signed approval binding |
| Existing failures prevent bug fixes | preserve executed failing Baseline without relabeling PASS; Full remains strict | test_baseline_regression |
| Historical DONE tasks block every later change | explicitly archive currently validated DONE without deleting evidence or reusing task IDs | test_archive |
| Records require undefined manual workflow | schema-backed attach command registers ADR/approval/exception without granting approval | test_lifecycle signed-review attach |

## Boundaries that remain external by design

- Human key custody, CI workflow protection, repository rules, production credentials and deployment authorization belong to the adopting organization. The CLI never generates a real human identity or authorizes deployment.
- A filesystem writer can change its own engine and evidence. Local hashes detect accidental or partial tampering; protected CI and externally trusted signatures supply the approval boundary. CI must pin the trust-file input and protect the workflow/engine used for validation.
- Path rules conservatively promote known paths, not semantically prove that arbitrary code has no security impact. Repository owners must tailor rules and reviewers must inspect scope.
- A configured check defines its own real test coverage. The engine checks execution and evidence, not whether a program named `security` is a comprehensive security test. Project adapters and acceptance mappings need actual project commands.
- Release is a readiness profile. This engine rejects commands labelled production and ships no deployment/migration executor. Staging readiness results cannot prove an actual production rollout succeeded.
- Windows local execution is measured in the delivery report. Linux and PowerShell 7 are specified in CI; their remote results are not claimed until that workflow runs.
