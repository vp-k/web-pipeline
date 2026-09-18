# Continuous development implementation plan

Scope: add a durable, skill-driven continuous development loop without changing human approval authority, resetting task iteration limits, or starting background model sessions.

1. Capture the existing executable baseline; preserve all existing tests.
2. Add a single project queue for explicitly selected tasks and dependencies. STATE.md remains the task-state owner; the queue owns only scheduling, leases, cursors and decision history.
3. Automatically advance valid state transitions and verification; hand implementation, failure repair and advisory code review to the active Codex session. A nonterminal action is not a reason to end the conversation.
4. Persist exclusive action tokens before execution; reject duplicate/stale acknowledgements. Interrupted work needs explicit recovery after inspecting actual effects, not blind replay.
5. Preserve per-task limits and add a durable queue step/time budget. Blocked tasks do not prevent independent queued work; dependencies and missing approvals still block the affected task.
6. Record selection reasons, alternatives, verification failures, implementation decisions and review rework with source/state/evidence identities. These are not human approvals or substitutes for required ADRs.
7. Test actual failure/repair/review loops, multiple tasks, approval waits, recovery, tamper/stale tokens, bounds and read-only status. Update the canonical skill, rebuild its checked-in distribution, and validate the resulting package.

No automatic production, commit/push, external account changes or unattended host restarts are in scope. A new host session can resume the persisted queue, but the package does not start that session itself.

## Executed result — engine/skill 2.2.0

- Pre-change baseline: [69 tests PASS](Reports/Pipeline/delivery-20260909T052944Z-33242614/delivery-validation.json).
- Final engine suite: [83 tests PASS](Reports/Pipeline/delivery-20260909T054706Z-a15dcfc4/delivery-validation.json), [full log](Reports/Pipeline/delivery-20260909T054706Z-a15dcfc4/unittest.log). Zero failures, errors or skips; Python 3.13.14 / Windows 11. Includes 14 new continuous-loop tests with actual verification processes and explicit fault injection.
- Distribution suite: [6 tests PASS](Reports/Pipeline/packaging-3bc5dbbb6890/packaging-validation.json), zero failures/errors/skips.
- Skill validation, plugin validation, module compilation, root kit validation and installed-cache doctor all passed. The rebuilt distribution contains 95 pipeline assets matching its inventory manifest.
- Repository skill snapshot refreshed at `skills/web-development-pipeline/`. Personal installed plugin updated and confirmed enabled as `2.2.0+codex.20260909054641`; use a new conversation to pick up the updated skill.
- Runtime queue/action/choice history is stored in the adopting project's `Docs/Work/AUTOPILOT.json`. This implementation's own choices and tradeoffs are in [CONTINUOUS_DECISIONS.md](CONTINUOUS_DECISIONS.md).
- No real human approval, live product DONE, production action, commit or push was performed. Remote CI and new-session agent behavior were not executed as part of this validation. Existing adopted projects still need an explicitly scoped engine upgrade before using loop commands.
