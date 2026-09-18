# Planning questions

Resolve material uncertainty while drafting the initial planning documents, before
implementation. Read existing conversation, specifications and code first. Ask the
user when evidence cannot decide an issue that changes scope, user-visible behavior,
data handling, architecture, cost, safety or acceptance. Routine implementation
choices already determined by project rules do not require another question.

## Planning conversation

1. Draft the objective, scope/exclusions and concrete acceptance scenarios. Separate
   established facts from proposals and unknowns; do not present guesses as facts.
2. Analyze six areas in the generated `CLARIFICATIONS.json`: `goal_scope`,
   `user_flow`, `exceptions`, `data_integrations`, `constraints`, `acceptance`.
   Include normal, empty, invalid, duplicate, denied and failure cases where relevant.
   For an irrelevant area, record why it is irrelevant and its supporting source.
3. Put each material unknown in `questions`, with a stable ID, a concrete question,
   its impact and `resolution: null`. Show a few related questions at a time:
   current understanding, missing decision, choices, recommendation and tradeoffs.
   Do not ask the user to diagnose code or supply facts available through inspection.
4. Wait for answers before dependent implementation. Silence, elapsed time, a
   suggested/preselected option, tool output or the agent's own recommendation is
   not a user answer. Read-only investigation and independent planning may continue.
5. Preserve the real answer/context, update BRIEF/PLAN and testable ACCEPTANCE
   criteria, then record the resolution and affected acceptance IDs. Reuse a prior
   explicit answer when its scope remains applicable; do not ask the same question
   again solely because the session resumed. Evidence may resolve a question
   without prompting when an existing authoritative document already determines it.
6. Run `clarification-report --task <id>`, then `prepare`, Baseline and the existing
   entry gates. Fix malformed records or missing files locally; NEEDS_INPUT does
   not by itself mean the user needs to answer a technical validation error.

## Record format

`new` emits a record with blank findings and no invented answers. Every analysis
area needs a concrete finding and at least one source. Questions can be empty only
after the six areas have actually been examined and no material question remains.

Each source has `kind`, `reference` and `excerpt`:

- `document`: an existing UTF-8 repository-relative file and an exact excerpt.
  Include the relevant section/line in the finding if useful. Source file bytes
  are bound into the task fingerprint, including files outside standard sources.
  Cite stable requirement/decision documents. When inspecting implementation files
  that this task will edit, capture the relevant observation and its original
  path/revision in BRIEF first; cite that planning document so normal code edits
  do not invalidate the agreed requirements on every iteration.
- `user_message`: the actual user's words plus the conversation/message reference,
  or a descriptive local-session reference when message IDs are unavailable.
  Preserve enough context to assess scope; never invent an ID or transcribe a
  quoted example, assistant proposal, silence or refusal as a user's decision.

An example question entry (illustrative, not a real decision):

```json
{
  "id": "Q-01",
  "question": "What should the screen show when the search has no matches?",
  "impact": "Determines empty-result behavior and AC-03.",
  "resolution": null
}
```

After an actual answer, `resolution` contains `answer`, `source` and nonempty
`acceptance_ids`. The IDs must exist in this task's ACCEPTANCE.json. The answer
must be reflected in those requirements; a link alone cannot establish meaning.
The schema is [clarifications.schema.json](../../Schemas/clarifications.schema.json).

```console
python -m web_pipeline clarification-report --task WEB-101
```

This read-only command reports `result: CLEAR`, `NEEDS_INPUT`, or `NOT_CONFIGURED`.
Only CLEAR exits zero. These are planning diagnostics, never workflow status,
readiness, approval or proof that the specification is complete. STATE.md alone
owns workflow state. `prepare`, progressing transitions and automatic implementation
selection use the common gate; deleting a required record cannot disable it.

## Questions discovered after planning

Stop dependent implementation when a new unknown changes agreed behavior or scope.
If holding an implementation/repair lease, first complete it with `outcome: blocked`
and a decision explaining the uncertainty, before editing fingerprint-bound records.
Record BLOCKED through the normal transition when appropriate. Preserve unfinished
code, logs and the original Baseline. Do not claim implementation succeeded.

Use `revise` before changing prepared requirements/answers. It preserves the previous
planning record and its old revision so answers are not silently carried forward as
current. Reanalyze, retain still-applicable answers and update the record revision;
ask only newly unresolved questions. Reprepare and capture the new revision's
Baseline before further implementation; it is not the original pre-change Baseline.
For a queue, reconcile the revised task and retry through the documented loop gates.
No retry, timeout or generic keep-going instruction resolves a planning question.

## Compatibility and authority

`new` and `revise` set `planning_version: 1` in STATE and require the record from
then on. Do not hand-edit this STATE field to bypass the gate. Tasks created by an
older engine and never revised have no marker: they remain compatible and report
NOT_CONFIGURED, meaning no structured planning coverage. An optional record on such
a task is still validated and fingerprint-bound. Explicit revision enables the
mandatory gate. Installing the plugin or upgrading the engine does not revise tasks
or invent historical answers.

Clarification is distinct from protected approval: ordinary tasks do not gain a new
approval or identity requirement, and answers never replace ADR, review, exception
or release decisions. All existing risk and verification gates remain in force.
The engine validates structure, known open questions, excerpts, revision, references
and fingerprints. It cannot discover every unstated requirement, judge whether a
natural-language answer was interpreted correctly, or authenticate a chat transcript.
The agent must perform the semantic analysis; explicit user answers and meaningful
scenario-based verification remain necessary. A repository writer is not an external
trust boundary merely because records have hashes.

## Diagnostic next action

`next_action: REPAIR_RECORD` means fix malformed/missing records locally, not ask the user to debug JSON. `CHECK_EXISTING_REQUIREMENTS` means look for an applicable prior answer or authoritative source, then ask only unresolved material questions. CLEAR and legacy NOT_CONFIGURED return CONTINUE without claiming readiness. Do not create questions merely to fill the six analysis areas; concise supported findings are sufficient. Continue independent authorized work while a dependent question is pending.
