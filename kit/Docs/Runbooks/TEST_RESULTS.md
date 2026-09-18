# Structured test verdicts

An exit code proves only process completion. Test commands can additionally declare:

```json
"test_report": {
  "path": "artifacts/tests.json",
  "min_tests": 1,
  "max_skipped": 0,
  "required_groups": ["unit"]
}
```

The real framework reporter writes `Schemas/test-results.schema.json`: run/check
identity from `PIPELINE_EVIDENCE_DIR` and `PIPELINE_CHECK_ID`, completed flag, runner
errors and individual case IDs/groups/statuses/durations. A reference Playwright
reporter ships in the plugin repository as `examples/web/reporter.cjs`; adoption does
not copy examples, so port it deliberately. Do not construct passing results by hand or
map an absent tool to a fake reporter. Retries must not hide earlier failed cases;
this reference disables retries. Other adapters must preserve retry failures or
report flaky results as failures until explicit policy supports them.

Zero exit plus missing/malformed/incomplete/stale report, zero executed tests,
duplicate IDs/keys, excess skips, unexecuted required groups, or failed/error cases
is FAIL. The parser derives counts from cases, bounds input size and rejects linked
or escaping paths. Logs and result files are hash-bound and revalidated at gates.
Baseline can retain conclusive failed cases with nonzero process exit, but cannot
capture a missing/incomplete/skip-only execution as a usable baseline.

The field is opt-in for compatibility: old commands remain exit-code-only checks,
not proof of test counts or coverage. `inspect` lists that distinction. Do not add
test counts to lint/build commands. Configure each real test adapter deliberately;
counts and group labels do not themselves prove semantic adequacy. Changing skip
allowances/minimums/required groups is a policy change, never an automatic repair
to make a failing implementation pass. Approved whole-check N/A remains N/A, not
an executed PASS.
