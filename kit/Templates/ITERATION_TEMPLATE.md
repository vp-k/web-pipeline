# Iteration Log

| Attempt | UTC time | Failure class | Fingerprint | Change | Result |
|---|---|---|---|---|---|

Usage and renewal grants are cumulative across revisions; revision never resets
them. `attempts` counts every Fast/Task/Phase/Full run, while `failed_attempts`
spends the failure budget. Record user-requested additional budget with `loop renew`,
not by editing limits or deleting history. Same-failure/external-retry and approval
gates remain separate and are not cleared by renew.
