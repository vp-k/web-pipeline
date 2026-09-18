# Review

This document is review analysis, not task status or approval. STATE.md owns status.

## Review kind

Standard unprotected T1/T2: local self-review; no human name required.
Standard protected/T3/T4: explicit user acceptance of current Full/review evidence.
Strict: independent signed human review is required separately.

## Findings

## Acceptance and regression assessment

## Decision

AI self-review may be recorded as supporting analysis but not as independent approval.

For standard unprotected T1/T2, record choice, rationale, alternatives and risks using
`review --task ... --decision <JSON>` after actual review in REVIEW state, or complete
the loop's REVIEW action with `reviewed`. The engine binds the local record to Full.

For standard protected/T3/T4, run `approval-request --task ... --phase review` in REVIEW state and record the user's acceptance with `approve`; the receipt binds the current tree, run ID and summary bytes.

In strict, an independent signed review binds the current fingerprint/tree, completion run ID, and SHA256 of that run's `summary.json` bytes. Use `attach --kind approval`; attachment alone does not validate the signature.
