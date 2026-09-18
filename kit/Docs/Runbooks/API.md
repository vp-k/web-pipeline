# API and Integration Runbook

For API, webhook and external-integration changes:

Read [BOUNDARIES.md](BOUNDARIES.md) and bind contract files to their provider and
consumer components and the four concrete contract checks. Contract files
participate in the source fingerprint. Shared types alone and mocked consumers alone
do not establish provider compatibility or a working frontend-to-backend flow.

The `api` and `external_integration` domains have a T2 floor. Changes to a public
API, webhook or third-party contract are the protected changes `public_api_contract`,
`webhook_contract` and `external_integration_contract` (T3, API Owner). Path rules
promote `*openapi*`, `*.graphql`, `*.proto` and `*webhook*` automatically; declare
the protected change on the task (`new --protected ...`) when the contract lives
elsewhere. A breaking change needs a version/deprecation plan in the EXEC_PLAN and
the protected design and review gates (standard receipts or strict signatures).

1. Use a canonical machine-readable contract (OpenAPI, GraphQL SDL, protobuf, JSON
   Schema) and generate or validate both sides from it. Record every contract
   change, its compatibility class and its consumers in
   [API_CONTRACT.md](../Architecture/API_CONTRACT.md) before implementation.
2. Verify real external payloads before writing code against them. Call the
   provider (or capture a real sample response) and check, field by field:
   - names: `snake_case` vs `camelCase`, `phone` vs `phoneNumber`;
   - formats: number vs numeric string, boolean vs `"Y"`, date vs datetime;
   - lengths and ranges against the columns and buffers that will store them;
   - presence: always sent, or omitted/`null` for some accounts or states.
   Dates and times usually arrive as full ISO datetimes (`1990-12-10T00:00:00.000Z`,
   24 characters), not `YYYY-MM-DD`; normalize on receipt or size storage for it.
   Field names and documentation are not evidence; the actual response is.
3. Verify provider and consumer behavior for authentication, timeouts, retries,
   idempotency keys, rate limits, pagination, signature validation and malformed or
   oversized payloads. Test the denied, expired and replayed cases, not only the
   happy path.
4. Never swallow write or parse errors. A `catch` that returns `false` turns a
   truncated column or a wrong format into "the value just is not there". Log
   "schema/column missing" separately from "data length/format error", with the
   field name, and fail the operation visibly. When several fields share one write,
   one bad value fails the whole statement; the log must say which.
5. When a value "does not show up", split the pipeline before changing code: call
   the external API directly, then query what was stored, then inspect the client.
   Fix the segment that is actually broken.
6. Run the domain's required checks: `contract-provider` and `contract-consumer`
   at Baseline/Fast; `contract-compatibility`, `integration` and `smoke` at Full;
   `security` at Release. External integrations add `webhook-tests` at Full.
   A missing or disabled required check fails the profile.

Webhooks are inbound untrusted input: validate the signature and timestamp before
parsing, deduplicate by event ID, and make handlers idempotent. Outbound calls use
non-production credentials and sandbox endpoints in every verification environment;
production endpoints are never an implied verification step.

For a new connected feature, define the contract first and use an explicit
[implementation group](IMPLEMENTATION_GROUPS.md) when provider and consumer code
must both exist for member completion tests. Task completion includes the
contracts of every affected participant; Full and Release include every declared
contract.
