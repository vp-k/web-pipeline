# Iteration Log

| Attempt | UTC time | Failure class | Fingerprint | Change | Result |
|---|---|---|---|---|---|

Usage and renewal grants are cumulative across revisions; revision never resets
them. `attempts` counts every Fast/Task/Phase/Full run, while `failed_attempts`
counts failures since the last covering PASS and spends the failure budget. Record user-requested additional budget with `loop renew`,
not by editing limits or deleting history. Approval gates are not cleared by renew. A
reached same-failure or external-retry stop is released only by a user-requested renew
that names the cause; a count below its stop is kept.
