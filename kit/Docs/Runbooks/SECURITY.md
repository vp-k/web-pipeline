# Security Runbook

For authentication, authorization, session, privacy and security changes:

Read [BOUNDARIES.md](BOUNDARIES.md) and [SECURITY_MODEL.md](../Architecture/SECURITY_MODEL.md).
The `authentication`, `authorization`, `security` and `privacy` domains have a T3
floor; the protected changes `authentication`, `authorization_rbac`, `session_cookie`,
`csrf_cors_csp`, `encryption` and `personal_data_pii` are T3, and `secrets_credentials`
is T4. Declare them on the task (`new --protected ...`) even when no path rule fires;
path rules (`*auth*`, `*session*`, `*.env*`, `*secret*`) only promote, never exempt.

1. Identify the trust boundary of every changed input: which values come from the
   browser, a third party or another service, and which are established server-side.
2. Treat all client state as untrusted: cookies, headers, query/body fields, hidden
   inputs, JWT claims before verification, and IDs the client claims to own.
   Re-derive identity and ownership on the server for every request.
3. Enforce authorization at the server boundary with both allowed and denied
   identities, including object-level checks (the right role and the wrong user).
   UI hiding is never authorization.
4. Keep secrets out of the repository, task documents, logs and evidence.
   `archive` refuses `.env*` (except `.env.example`/`.env.template`/`.env.sample`),
   private keys and keystores; a check that prints a credential into
   `PIPELINE_EVIDENCE_DIR` has leaked it. Use non-production credentials for every
   verification environment.
5. Treat dependency and lockfile changes as security work: `*.lock`, `*-lock.json`,
   `*-lock.yaml`, `*.lockb`, `*npm-shrinkwrap.json`, `*go.sum`, `*go.mod`,
   `*package.json` and `requirements*.txt` classify as `major_framework_sdk` (T3).
   Review the upstream change, not only the version bump.
6. Run the domain's required checks: `security` (and `secret-detection` for
   `secrets_credentials`), plus `session-tests` and `authorization-tests` for
   authentication work. A missing or disabled required check fails the profile.

Test at least:

- unauthenticated, expired/revoked session, and wrong-user access;
- role and object-level authorization denial;
- CSRF/session/cookie behavior (SameSite, Secure, HttpOnly, rotation on login);
- malformed and boundary inputs, including oversized and wrongly typed values;
- secret and personal-data leakage in logs, error responses and evidence;
- safe defaults and failure behavior (deny on error, no fallback to permissive).

Security design and risk acceptance are governed decisions, not implementation
choices. Protected work needs a design receipt before READY and a review receipt
before DONE: in standard policy, scoped user receipts through `approval-request`
then `approve`, covering the configured owner roles (Security Owner, Data Owner);
in strict policy, signed records from the trusted humans holding those roles. An
AI may draft the threat model and the ADR but may not supply either approval.
