# Risk Classification

Risk is modeled using three independent axes.

| Axis | Question |
|---|---|
| `risk_tier` | How large is the potential impact? |
| `change_domains` | Which technical or governance areas are affected? |
| `protected_changes` | Is a human-owned decision mandatory? |

The computed tier is the maximum of the requested tier, every affected-domain floor, every protected-change floor, and the migration-class floor. The pipeline never automatically lowers a tier. Ambiguity promotes the tier.

## Tiers

| Tier | Typical examples | Minimum records | Approval (unprotected) |
|---|---|---|---|
| T0 | Copy, comments, isolated visual CSS | STATE, BRIEF, DOR, ACCEPTANCE, CLARIFICATIONS and Baseline/completion-profile evidence | None |
| T1 | Small bug, single component/internal behavior | T0 + verification + review | Local self-review in standard; signed Reviewer in strict |
| T2 | General feature, API addition, multi-file flow | T1 + PLAN + acceptance mapping | Local self-review in standard; signed Reviewer and Tech Owner design approval in strict |
| T3 | Auth, privacy, public contract, schema, architecture | T2 + EXEC_PLAN + accepted ADR/risk record | Standard: scoped user receipts for the design (Tech Owner responsibility) and review (Reviewer) phases. Strict: signed Tech Owner design approval and signed independent Reviewer |
| T4 | Production deploy/migration, payment, production data/credentials | T3 + RELEASE record and recovery/rollback plan | T3 gates plus a separate release decision: standard, one receipt covering Release Owner and every affected responsibility; strict, at least two distinct human signers, neither the implementer |

Any protected change adds its configured owner roles (`risk.protected_rules`) to
the design and release phases, whatever the tier. In standard those roles describe
the responsibilities one scoped user receipt must cover; in strict each role needs a
signature from a trusted identity holding that role.

## Change domains

Standard's local review applies only to unprotected T0–T2; it never lowers the
computed tier or overrides protected-change, exception or Release authority.

Allowed values:

```text
frontend
backend
database
api
authentication
authorization
security
privacy
payment
external_integration
infrastructure
deployment
```

Domain selection drives verification. For example:

| Domains | Expected checks |
|---|---|
| frontend | lint, typecheck, unit, browser E2E, visual evidence, build |
| backend + api | lint, typecheck, unit, contract, integration |
| database | migration/schema checks, integration, dry-run and rollback when applicable |
| authentication + authorization | security, authorization-negative tests, session tests, ADR and owner approval |

## Automatic promotion examples

- Login API with role enforcement: requested T1 -> computed T3; `backend`, `api`, `authentication`, `authorization`; protected.
- Nullable internal column with backward-compatible rollout: at least T3 because it changes the database schema; reversible execution may remain below T4 if it does not touch production.
- Dropping a production balance column: T4; database, payment/production data; destructive migration.
- Static color adjustment: normally T0 frontend, unless it changes a security-meaningful state or accessibility acceptance criterion.
