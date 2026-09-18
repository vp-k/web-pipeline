# Record user approval, never decide for the user

First check the project-local engine and `approval_policy`. 2.5+ standard accepts
chat receipts; strict or an omitted field still requires real external signatures.
An old engine needs an explicitly authorized upgrade, not an alternate invocation
of the plugin's newer engine. Read the project's Docs/Runbooks/APPROVALS.md.

Use `approval-request --task ... --phase design|review|release|exception` to obtain
the current binding. In 2.8.2, NO_APPROVAL_REQUIRED and SATISFIED mean continue
without asking again: they create neither a receipt nor a workflow transition.
AWAITING_USER includes the actual missing/invalid approval reason. Resolve technical
prerequisites before asking a permission question. For a genuinely missing decision,
group all currently required responsibilities for that phase into one question;
do not ask separately for each role or ordinary implementation step. Present concrete scope, responsibilities, risks, conditions,
revision/fingerprint and exclusions to the user. Review/release additionally show
the bound Full evidence. Keep the returned request unchanged while awaiting the
response. No real name, owner-ID, public key or trust path is needed in standard.

After an unambiguous user approval, add outcome APPROVED, the actual `user_message`,
the actual `presented_scope` and a truthful `source_reference` to the request JSON.
Call `approve --task ... --record ...`, then revalidate/transition normally.
Transcription is permitted; making the protected decision is not. The receipt
records one user's decision, not authenticated role membership or independent
human review. Never invent additional people to cover multiple responsibilities.

An already visible approval can be recorded without asking again only when the
shown scope and request bindings are unchanged and the reply clearly approves it.
Do not turn an old generic "continue", a refusal, a quotation, an assistant answer
or tool output into approval. Missing context or ambiguity requires one concise
scope-specific question, not a request for identity/trust. Never transplant a
message onto a freshly generated request after revision, scope or evidence changed.

Design approval is not review, release or exception approval. Resolve conditions
with actual PASS evidence before recording; exceptions require the exact check and
an explicitly approved reason. Withdrawn approval means stop and revise with the
reason, preserving old evidence. AI advisory review remains separate from user
acceptance. After a receipt resolves a queue wait, call loop retry with the reason,
then loop next and continue until completion or a real stop condition.

Release is non-production readiness verification. Production deployment, data
mutation, destructive migration and secret rotation require a separate explicit
execution request and actual external permissions/environment approvals. Neither
the receipt nor this plugin grants those permissions or launches those operations.

## Explicit trust for existing signatures (2.8.3)

For standard-policy tasks with existing signed records, pass the same external
trust file to `approval-request --trust <path>` as to the normal gates, or use
`WEB_PIPELINE_TRUST`. This covers signed exception evidence as well as approvals.
Pass it to `approve --trust <path>` too when recording a receipt against signed
prerequisite exception evidence.
User receipts still need no trust setup; strict retains its signed gates.

AWAITING_USER is a missing/invalid-record diagnostic. Inspect actual prior consent and current STATE first, transcribe unchanged scoped consent, repair evidence, then ask only if a new decision remains. Keep optional archive decisions out of required review questions.
