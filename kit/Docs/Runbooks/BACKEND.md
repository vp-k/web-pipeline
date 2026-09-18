# Backend Runbook

For backend changes:

Read [BOUNDARIES.md](BOUNDARIES.md). Keep authorization, business rules, database
access and secrets server-side; share neutral contracts rather than implementations.
Identify API consumers and execute their compatibility/integration checks too.

A small connected feature may be one task spanning both sides. For deliberately
split tasks, when both sides must be implemented before connected tests can
pass, follow [implementation groups](IMPLEMENTATION_GROUPS.md): contract and scope
first; every member Baseline/entry gate; backend then frontend implementation;
unchanged member checks/review; finally Phase checks/review. Do not make the
frontend wait for backend DONE when backend DONE requires that frontend to exist.

1. Identify trust boundaries, API/data contracts, idempotency, retries, and failure semantics.
2. Validate all client input server-side.
3. Test authorization using both allowed and denied identities.
4. Run unit, contract, integration, and build/smoke checks as applicable.
5. Confirm logs avoid credentials and unnecessary personal data.
