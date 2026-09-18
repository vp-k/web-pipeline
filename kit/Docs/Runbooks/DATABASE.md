# Database Runbook

For database and schema changes:

Read [BOUNDARIES.md](BOUNDARIES.md) and [DATA_CONTRACT.md](../Architecture/DATA_CONTRACT.md).
The `database` domain has a T2 floor. Declare the migration class on the task
(`new --migration <class>`); the engine raises the tier to the class floor and adds
the protected changes below. Path rules promote `*migration*` and `*.sql` to
`database_schema` (T3) regardless of the declared class.

| Migration class | Tier floor | Protected changes | Implication |
|---|---|---|---|
| `none` | T0 | – | Data access only; no DDL |
| `reversible` | T2 (T3 via `database_schema`) | `database_schema` | Additive or fully undoable DDL; rollback validated |
| `backward_compatible` | T3 | `database_schema` | Old and new code run against the schema during deploy; expand/contract order documented |
| `destructive` | T4 | `database_schema`, `destructive_migration` | Data or structure is lost; restore validated and RELEASE record required; release receipt before Release readiness, separate explicit authority before production execution |
| `irreversible` | T4 | `database_schema`, `destructive_migration` | Cannot be undone even with a restore of the schema; recovery plan and Data Owner responsibility required |

`database_schema` names the DB Owner; `destructive_migration` adds the Data Owner.
In standard policy, one scoped user receipt per gate covers those responsibilities;
in strict policy, each role signs. Classify conservatively: a column type change or
a `NOT NULL` backfill is destructive if any live row cannot survive it.

1. Classify the migration and record class, deployment order and mixed-version
   compatibility in the PLAN or EXEC_PLAN compatibility/migration section.
2. Test against the real engine the project ships on, with the real migration files.
   Use `testcontainers` (`@testcontainers/postgresql` for Postgres) and run the
   production migration path into the container; never a schema-sync shortcut and
   never SQLite or an in-memory substitute. NULL handling in UNIQUE, locking hints,
   JSON support and timestamp defaults differ enough that a substitute passes what
   the real engine fails, and sync tools drop hand-written migration SQL.
3. Test forward migration against representative non-production data, including
   empty tables, maximum-length values and rows that violate the new constraint.
4. Validate rollback for reversible changes, or restore/recovery for destructive
   and irreversible changes, from an actual backup, not from a fresh schema.
5. Measure locking, duration and capacity risk for large tables; plan batching and
   online index creation where the engine supports it.
6. Parameterize every value in raw SQL (`$1`, `$2` placeholders with a separate
   argument list). Never interpolate a value into the statement string.
7. Allowlist dynamic identifiers immediately before interpolation. `ORDER BY` and
   `GROUP BY` columns cannot be placeholders, so the function that builds the string
   must itself check the column against a fixed map and fall back to a safe default,
   and normalize direction to `ASC`/`DESC`. Do not rely on an upper layer having
   sanitized the value; revalidate at the point of use. Any `%s`/`${}` inside a
   SQL string is a review checkpoint.
8. Check fixed-width columns against real maximum lengths of the values that will
   land in them, especially values from external APIs (dates arrive as 24-character
   ISO datetimes; tokens, URLs and emails are longer than assumed). Size
   `VARCHAR(N)` from observed data, not from the field name.
9. Never swallow write errors: distinguish "column missing, migration needed" from
   "value too long/wrong format", log the field, and fail loudly. One truncated
   value fails every column bound in the same statement.
10. Run the domain's required checks: `schema-check` and `integration` at Baseline,
    `schema-check` at Fast, plus `migration-dry-run` and `rollback-validation` at
    Full; Release adds `restore-validation`, and destructive migrations add
    `recovery-validation`. A missing or disabled required check fails the profile.
11. Never execute against production as an implied implementation or verification
    step. Production migration is a T4 deployment decision with its own release
    receipt or signatures, executed outside the pipeline's commands.
