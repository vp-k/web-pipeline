# Protected Changes

Protected changes require a human-owned decision and may raise the risk tier. The configured identifiers are:

```text
authentication
authorization_rbac
session_cookie
csrf_cors_csp
encryption
secrets_credentials
personal_data_pii
payment
wallet_balance
database_schema
destructive_migration
production_data
public_api_contract
webhook_contract
external_integration_contract
core_architecture
major_framework_sdk
infrastructure
production_deployment
dns_cdn_waf
```

An AI may investigate, implement within an approved design, draft an ADR, and produce verification evidence. It cannot approve the decision, accept the risk, or impersonate the named owner.

## Database migration classes

| Class | Meaning | Minimum treatment |
|---|---|---|
| NONE | No schema/data migration | No migration gate |
| REVERSIBLE | Deterministically reversible without data loss | Migration test and rollback procedure |
| BACKWARD_COMPATIBLE | Expand/contract safe across mixed versions | T3, compatibility window and cleanup plan |
| DESTRUCTIVE | Drops/rewrites data or removes compatibility | T4, recovery proof and multiple approval |
| IRREVERSIBLE | No credible rollback | T4, restore/recovery evidence and explicit risk acceptance |

`ADD nullable_column` and `DROP COLUMN balance` must never receive the same treatment merely because both are schema changes.

## Stop conditions

Stop and record BLOCKED when a required owner, valid approval, safe test environment, recovery evidence, source revision, or credential boundary is absent. Do not solve the absence by weakening the policy.

