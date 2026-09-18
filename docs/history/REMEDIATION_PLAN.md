# 2026-09-09 review remediation

Scope: fix the eleven reproduced review findings without production actions or fabricated human approvals. This is implementation planning, not task approval.

1. Record an executed pre-change suite baseline. Add regressions for each reproduced path.
2. Split progress validation from an explicit merge gate; require all active tasks DONE and current evidence/signatures for merge. Route Policy through the common validator.
3. Validate all output exclusions against tracked code and governed inputs. Freeze Baseline after DRAFT; require revise to reopen BLOCKED work as DRAFT.
4. Include task Acceptance checks in Full/Release and reject unreachable checks during prepare. Count actual failures only, and preflight run IDs before changing state.
5. Restrict shell hosts to explicit script invocation and make PowerShell adapters independent of caller working directory.
6. Preserve exact verified source bytes in an archive ZIP and hash manifest matching the approved Full tree digest.
7. Connect a PR-triggered project merge gate, document evidence delivery and external trust setup, and preserve kit-only validation for this non-ready kit.
8. Execute the expanded suite, adapter diagnostics, and sample lifecycle; retain results. Add real web-stack integration only when an actual project/environment is in scope. Human key custody and repository protection remain external requirements.

Archive timing: merge the completed active change set first. Archive before beginning the next change set; archive-only changes still need an active housekeeping task if submitted through the merge gate.

Structured zero-test/skip and semantic test-weakening detection are not silently claimed by an exit-code runner. Their project adapters and evidence contracts remain explicitly documented follow-up work.

## Executed result

All eight scoped steps above were implemented and locally verified. The kit remains NOT_READY for an adopting project's operations until real commands, source documents, external trust and protected CI are configured.

- Pre-change baseline: [51 tests PASS](Reports/Pipeline/delivery-20260909T031208Z-7af43224/delivery-validation.json).
- Final suite: [69 tests PASS; zero failures, errors or skips](Reports/Pipeline/delivery-20260909T032900Z-8d272285/delivery-validation.json), [full log](Reports/Pipeline/delivery-20260909T032900Z-8d272285/unittest.log). Runtime: Python 3.13.14 on Windows 11.
- Module compilation and kit validation passed. Actual Windows PowerShell 5.1 validation and installation from outside the repository passed within the regression suite.
- The installed minimal example executed Baseline and Full and stopped at REVIEW, without fabricating a Reviewer approval. Evidence: `E:/code/web-pipeline-example-evidence-20260909-v21`.
- PR merge-gate wiring and CI context were checked locally; remote Actions, Linux and PowerShell 7 execution are NOT_RUN. No production action or actual human approval was performed.

See [review resolution](REVIEW_RESOLUTION.md) for the finding-to-fix mapping and remaining external boundaries.
