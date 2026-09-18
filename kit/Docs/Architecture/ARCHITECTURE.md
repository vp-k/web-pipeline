# Web Architecture

Status: DRAFT  
Revision: UNSET

## Boundary model

```text
Untrusted browser
      |
      | HTTPS + API contract
      v
Backend trust boundary
      |
      | schema/migration contract
      v
Database

Backend ---- webhook/API contract ---- External services
```

Frontend, backend, database, and external services may share generated types, but generated code is not the source of truth. Prefer an explicit OpenAPI, JSON Schema, protocol schema, or equivalent contract that each consumer validates.

## Required architecture records

Declare runtime ownership and permitted imports with the engine's optional
`boundaries` model; see [boundary configuration](../Runbooks/BOUNDARIES.md).
For a newly adopted web project configure it before claiming isolation. Physical
repository/service separation is optional; client/server trust separation is not.
Record API provider/consumers and integrated-flow checks alongside import rules.

- Components and ownership
- Trust boundaries and data flows
- Authentication and server-side authorization
- API compatibility/version policy
- Data classification, retention, deletion, and recovery
- External integration failure behavior
- Deployment topology and rollback strategy
- Observability and incident signals

Architecture-changing tasks use an attached accepted ADR for the current task revision plus a separate design approval matching the current fingerprint and protected scope: a user receipt in standard or a signature in strict.
