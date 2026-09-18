from __future__ import annotations

from pathlib import Path
import re
from typing import Any

from .approval import validate_approvals
from .local_review import ordinary_work, validate_review
from .budget import new_accounting
from .common import (PipelineError, atomic_json, atomic_text, code_snapshot, load_config,
                     lock, read_state, safe_path, source_fingerprint, utc_now, validate_schema, write_state)
from .policy import TIERS, classify, document_errors, option_shaped

STATUSES = ("DRAFT", "READY", "IN_PROGRESS", "VERIFYING", "REVIEW", "DONE", "BLOCKED")
TRANSITIONS = {
    "DRAFT": {"READY", "BLOCKED"}, "READY": {"IN_PROGRESS", "BLOCKED"},
    "IN_PROGRESS": {"VERIFYING", "BLOCKED"}, "VERIFYING": {"REVIEW", "BLOCKED"},
    "REVIEW": {"DONE", "IN_PROGRESS", "BLOCKED"}, "DONE": set(),
    "BLOCKED": {"READY", "IN_PROGRESS"},
}


def create_task(root: Path, task_id: str, title: str, tier: str, domains: list[str],
                protected_changes: list[str] | None = None, migration_class: str = "none",
                base_ref: str | None = None) -> dict[str, Any]:
    root = Path(root).resolve()
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{1,63}", task_id):
        raise PipelineError("task_id must be 2-64 safe identifier characters")
    if tier not in TIERS or not title.strip() or not domains:
        raise PipelineError("title, valid tier, and at least one domain are required")
    if option_shaped(base_ref):
        raise PipelineError(f"base_ref {base_ref!r} must be a git revision, not an option")
    task_dir = safe_path(root, f"Docs/Work/{task_id}")
    archive_dir = safe_path(root, "Docs/Archive")
    if archive_dir.is_dir() and any(
        re.fullmatch(re.escape(task_id) + r"-r[0-9]+", entry.name)
        for entry in archive_dir.iterdir() if entry.is_dir()
    ):
        raise PipelineError(f"task_id has archived history and cannot be reused: {task_id}")
    now = utc_now()
    state = {"schema_version": "2.0", "planning_version": 1, "task_id": task_id, "title": title.strip(),
             "status": "DRAFT", "revision": 1, "requested_tier": tier, "risk_tier": tier,
             "change_domains": sorted(set(domains)), "protected_changes": sorted(set(protected_changes or [])),
             "migration_class": migration_class, "base_ref": base_ref, "implementer": None,
             "fingerprint": None, "approvals": [], "decision_records": [], "exceptions": [],
             "baseline_run": None, "full_run": None, "release_run": None,
             "iteration": {"attempts": 0, "same_failure": 0, "external_retries": 0,
                           "started_utc": None, "last_failure": None, **new_accounting(task=True)},
             "release_status": "NOT_READY", "blockers": [], "created_utc": now, "updated_utc": now}
    config = load_config(root, kit=True)
    result = classify(root, config, state)
    if result["errors"]:
        raise PipelineError("; ".join(result["errors"]))
    for key in ("risk_tier", "change_domains", "protected_changes"):
        state[key] = result[key]
    validate_schema(root, "state", state)
    with lock(root, f"task-{task_id}"):
        if task_dir.exists():
            raise PipelineError(f"task already exists: {task_id}")
        if archive_dir.is_dir() and any(
            re.fullmatch(re.escape(task_id) + r"-r[0-9]+", entry.name)
            for entry in archive_dir.iterdir() if entry.is_dir()
        ):
            raise PipelineError(f"task_id has archived history and cannot be reused: {task_id}")
        task_dir.mkdir(parents=True)
        atomic_text(task_dir / "BRIEF.md", f"# {title.strip()}\n\n## Scope\n\nTBD\n")
        atomic_text(task_dir / "DOR.md", "# Definition of Ready\n\n- Baseline intent: NOT_RUN\n")
        atomic_json(task_dir / "ACCEPTANCE.json", {"criteria": []})
        from .clarifications import template
        atomic_json(task_dir / "CLARIFICATIONS.json", template(state))
        if TIERS.index(state["risk_tier"]) >= 2:
            atomic_text(task_dir / "PLAN.md", "# Implementation Plan\n\nTBD\n")
        if TIERS.index(state["risk_tier"]) >= 3:
            atomic_text(task_dir / "EXEC_PLAN.md", "# Execution and Recovery Plan\n\nTBD\n")
        if TIERS.index(state["risk_tier"]) >= 4:
            atomic_text(task_dir / "RELEASE.md", "# Release Readiness and Recovery\n\nTBD\n")
        write_state(root, state)
    return state


def prepare_task(root: Path, task_id: str, implementer: str = 'claude') -> dict[str, Any]:
    """Seal a DRAFT revision so Baseline can bind to a stable task fingerprint."""
    root = Path(root).resolve()
    if not implementer.strip():
        raise PipelineError("implementer identity is required")
    with lock(root, f"task-{task_id}"):
        is_kit = config_mode_is_kit(root)
        config = load_config(root, kit=is_kit)
        state = read_state(root, task_id)
        if state["status"] != "DRAFT":
            raise PipelineError("only DRAFT tasks can be prepared; revise the task first")
        if not is_kit and not state.get("base_ref"):
            raise PipelineError("project tasks require an explicit Git base_ref")
        result = classify(root, config, state)
        if result["errors"]:
            raise PipelineError("; ".join(result["errors"]))
        for key in ("risk_tier", "change_domains", "protected_changes"):
            state[key] = result[key]
        from .scopes import task_scope
        task_scope(root, config, state)
        problems = document_errors(root, state)
        import json
        acceptance = json.loads((root / "Docs" / "Work" / task_id / "ACCEPTANCE.json").read_text(encoding="utf-8-sig"))
        validate_schema(root, "acceptance", acceptance)
        definitions = {command['id']: command for command in config['verification']['commands']}
        known = set(definitions)
        unknown = {check_id for item in acceptance["criteria"] for check_id in item["checks"]} - known
        if unknown:
            problems.append(f"acceptance references unknown checks: {sorted(unknown)}")
        for check_id in {check for item in acceptance['criteria'] for check in item['checks']} - unknown:
            command = definitions[check_id]
            if not command['enabled'] or not {'Full', 'Policy'}.intersection(command['profiles']):
                problems.append(f'Acceptance check {check_id} must be enabled and executable in Full')
        if problems:
            raise PipelineError("; ".join(problems))
        state["implementer"] = implementer.strip()
        state["fingerprint"] = source_fingerprint(root, config, state)
        state["updated_utc"] = utc_now()
        write_state(root, state)
        return state


def config_mode_is_kit(root: Path) -> bool:
    import json
    raw = json.loads((root / "pipeline.config.yaml").read_text(encoding="utf-8-sig"))
    return raw.get("project", {}).get("mode") == "kit"


def attach_record(root: Path, task_id: str, kind: str, relative: str) -> dict[str, Any]:
    """Register a candidate record; only the relevant gate can validate approval."""
    import json
    root = Path(root).resolve()
    fields = {'adr': 'decision_records', 'approval': 'approvals', 'exception': 'exceptions'}
    if kind not in fields:
        raise PipelineError('Unknown record kind')
    with lock(root, f'task-{task_id}'):
        state = read_state(root, task_id)
        path = safe_path(root, relative, must_exist=True)
        record = json.loads(path.read_text(encoding='utf-8-sig'))
        chat = kind != 'adr' and record.get('kind') == 'user_approval'
        validate_schema(root, 'user-approval' if chat else kind, record)
        if chat and load_config(root, kit=config_mode_is_kit(root)).get('approval_policy', 'strict') != 'standard':
            raise PipelineError('Strict policy requires signed approvals, not user receipts')
        payload = record if kind == 'adr' else record['payload']
        if payload['task_id'] != task_id or payload['revision'] != state['revision']:
            raise PipelineError('Record task/revision does not match current task')
        if kind == 'adr' and (state['status'] != 'DRAFT' or state['fingerprint'] is not None):
            raise PipelineError('Attach ADR before prepare; revise a prepared task first')
        if kind == 'approval' and payload['phase'] == 'exception':
            raise PipelineError('Exception records must use kind exception')
        if kind == 'exception' and payload['phase'] != 'exception':
            raise PipelineError('Only exception-phase records may be attached as exceptions')
        if kind != 'adr' and payload['fingerprint'] != state['fingerprint']:
            raise PipelineError('Record fingerprint does not match prepared task')
        normalized = path.relative_to(root).as_posix()
        records = state[fields[kind]]
        if normalized not in records:
            records.append(normalized)
            state['updated_utc'] = utc_now()
            write_state(root, state)
        return state


def _validate_acceptance(root: Path, task_id: str, summary: dict[str, Any]) -> None:
    import json
    acceptance = json.loads((root / "Docs" / "Work" / task_id / "ACCEPTANCE.json").read_text(encoding="utf-8-sig"))
    ids = [item["id"] for item in acceptance["criteria"]]
    if len(ids) != len(set(ids)):
        raise PipelineError("acceptance criterion IDs must be unique")
    checks = summary.get("checks", [])
    passed = {check["id"] for check in checks if check.get("status") in {"PASS", "NOT_APPLICABLE"}}
    known = {check["id"] for check in checks}
    unknown = [(item["id"], check_id) for item in acceptance["criteria"]
               for check_id in item["checks"] if check_id not in known]
    unmet = [(item["id"], check_id) for item in acceptance["criteria"]
             for check_id in item["checks"] if check_id not in passed]
    if unknown:
        raise PipelineError(f"acceptance criteria reference checks absent from evidence: {unknown}")
    if unmet:
        raise PipelineError(f"acceptance criteria lack PASS evidence: {unmet}")


def _roles(config: dict[str, Any], state: dict[str, Any], phase: str) -> list[str]:
    roles: set[str] = set()
    tier = TIERS.index(state["risk_tier"])
    if phase in {'design', 'review'} and ordinary_work(config, state):
        return []
    if phase == "review" and tier >= 1:
        roles.add("Reviewer")
    if phase == "design":
        if tier >= 2 and not state.get("protected_changes"):
            roles.add("Tech Owner")
        for change in state.get("protected_changes", []):
            roles.update(config["risk"]["protected_rules"][change].get("roles", []))
    if phase == "release":
        roles.add("Release Owner")
        for change in state.get("protected_changes", []):
            roles.update(config["risk"]["protected_rules"][change].get("roles", []))
    return sorted(roles)


def _review_gate(root, config, state, trust_path, snapshot):
    if ordinary_work(config, state) and state['risk_tier'] != 'T0':
        validate_review(root, config, state, snapshot)
    else:
        validate_approvals(root, config, state, _roles(config, state, 'review'), 'review',
                           trust_path, snapshot, state.get('full_run'))


def policy_check(root: Path, task_id: str | None = None, kit: bool = False,
                 trust_path: str | Path | None = None, base_ref: str | None = None,
                 gate: str = 'progress') -> dict[str, Any]:
    root = Path(root).resolve()
    errors: list[str] = []
    warnings: list[str] = []
    if safe_path(root, 'Docs/Work/ARCHIVE_PENDING.json').exists():
        return {'status': 'FAIL', 'errors': ['Interrupted archive requires archive --recover'], 'warnings': []}
    if gate not in {'progress', 'merge'} or (gate == 'merge' and (kit or task_id)):
        return {'status': 'FAIL', 'errors': ['Merge gate requires a strict, all-active-task scan; no --kit or --task'], 'warnings': []}
    try:
        config = load_config(root, kit=kit)
        if gate == 'merge':
            from .git_state import require_settled_checkout
            require_settled_checkout(root)
    except PipelineError as exc:
        return {"status": "FAIL", "errors": [str(exc)], "warnings": []}
    if 'boundaries' not in config:
        warnings.append('Boundary validation NOT_CONFIGURED: declare project source/runtime boundaries; no import isolation is proven')
    work_root = root / "Docs" / "Work"
    task_ids = [task_id] if task_id else sorted(p.name for p in work_root.iterdir() if p.is_dir()) if work_root.is_dir() else []
    if not task_ids:
        # Configuration is still validated; only a merge gate needs work to inspect.
        (errors if gate == 'merge' else warnings).append("no tasks found")
    from .scopes import phase_coverage
    coverage = phase_coverage(root, config, trust_path) if not kit else {}
    for current in task_ids:
        try:
            state = read_state(root, current)
            validate_schema(root, "state", state)
            from .clarifications import inspect as inspect_planning
            planning = inspect_planning(root, state)
            if planning['result'] == 'NOT_CONFIGURED':
                warnings.append(f'{current}: planning clarification NOT_CONFIGURED; revise to enable structured planning')
            if gate == 'merge' and state['status'] != 'DONE':
                errors.append(f"{current}: merge gate requires DONE, found {state['status']}")
            if not kit and not state.get("base_ref"):
                errors.append(f"{current}: project task requires base_ref")
            candidate = dict(state)
            if base_ref is not None:
                if option_shaped(base_ref):
                    raise PipelineError(f"base_ref {base_ref!r} must be a git revision, not an option")
                candidate["base_ref"] = base_ref
            result = classify(root, config, candidate, changed_paths=coverage.get(current))
            errors.extend(f"{current}: {e}" for e in result["errors"])
            warnings.extend(f"{current}: {w}" for w in result["warnings"])
            for key in ("risk_tier", "change_domains", "protected_changes"):
                if state[key] != result[key]:
                    errors.append(f"{current}: stored {key} is stale; computed {result[key]}")
            if state["status"] != "DRAFT":
                errors.extend(f"{current}: {e}" for e in document_errors(root, state, for_done=state["status"] == "DONE"))
            if state.get("fingerprint") and source_fingerprint(root, config, state) != state["fingerprint"]:
                errors.append(f"{current}: source fingerprint is stale")
            if state["status"] in {"READY", "IN_PROGRESS", "VERIFYING", "REVIEW", "DONE"}:
                if not state.get("fingerprint") or not state.get("implementer"):
                    raise PipelineError("prepared fingerprint and implementer are required")
                validate_approvals(root, config, state, _roles(config, state, "design"), "design", trust_path)
                if not state.get("baseline_run"):
                    raise PipelineError("Baseline run is required")
                from .runner import validate_run, validate_completion
                validate_run(root, config, state, state["baseline_run"], "Baseline", require_current=False, trust_path=trust_path)
            if state["status"] in {"REVIEW", "DONE"}:
                from .runner import validate_run, validate_completion
                if not state.get("full_run"):
                    raise PipelineError("Completion run is required")
                summary = validate_completion(root, config, state, state["full_run"], require_current=current not in coverage, trust_path=trust_path)
                _validate_acceptance(root, current, summary)
            if state["status"] == "DONE":
                snapshot = summary["snapshot"] if current in coverage else code_snapshot(root, config)
                _review_gate(root, config, state, trust_path, snapshot)
            if state.get("release_status") in {"READY", "VERIFIED"}:
                from .runner import validate_run, validate_completion
                if state['status'] != 'DONE' or state['risk_tier'] != 'T4':
                    raise PipelineError('Release readiness requires DONE T4')
                if not state.get("release_run"):
                    raise PipelineError("release status requires a Release run")
                release = validate_run(root, config, state, state["release_run"], "Release", True,
                                       trust_path=trust_path)
                _validate_acceptance(root, current, release)
                validate_approvals(root, config, state, _roles(config, state, "release"), "release",
                                   trust_path, code_snapshot(root, config), state["full_run"])
        except (PipelineError, OSError, ValueError, KeyError) as exc:
            errors.append(f"{current}: {exc}")
    return {"status": "PASS" if not errors else "FAIL", "errors": errors, "warnings": warnings}


def transition(root: Path, task_id: str, status: str, trust_path: str | Path | None = None) -> dict[str, Any]:
    root = Path(root).resolve()
    if status not in STATUSES:
        raise PipelineError(f"invalid status: {status}")
    with lock(root, f"task-{task_id}"):
        is_kit = config_mode_is_kit(root)
        config = load_config(root, kit=is_kit)
        state = read_state(root, task_id)
        if status not in TRANSITIONS[state["status"]]:
            if status == 'DRAFT':
                raise PipelineError('Use revise to return to DRAFT and increment revision')
            raise PipelineError(f"invalid transition: {state['status']} -> {status}")
        if status == "READY" and is_kit:
            raise PipelineError("kit-mode tasks cannot enter READY")
        result = classify(root, config, state)
        if result["errors"]:
            raise PipelineError("; ".join(result["errors"]))
        for key in ("risk_tier", "change_domains", "protected_changes"):
            state[key] = result[key]
        if status in {"IN_PROGRESS", "VERIFYING", "REVIEW", "DONE"}:
            problems = document_errors(root, state)
            if problems:
                raise PipelineError("; ".join(problems))
            if not state.get("implementer") or not state.get("fingerprint"):
                raise PipelineError("task must be prepared before progressing")
            if source_fingerprint(root, config, state) != state["fingerprint"]:
                raise PipelineError("task fingerprint is stale; revise the task")
            validate_approvals(root, config, state, _roles(config, state, "design"), "design", trust_path)
            if not state.get("baseline_run"):
                raise PipelineError("Baseline run is required")
            from .runner import validate_run, validate_completion
            validate_run(root, config, state, state["baseline_run"], "Baseline", require_current=False, trust_path=trust_path)
        if status == "READY":
            problems = document_errors(root, state)
            if not state.get("implementer"):
                problems.append("READY requires an identified implementer")
            if problems:
                raise PipelineError("; ".join(problems))
            if not state.get("fingerprint") or source_fingerprint(root, config, state) != state["fingerprint"]:
                raise PipelineError("task must be prepared with a current fingerprint; revise after changing scope or docs")
            from .runner import validate_run, validate_completion
            if not state.get("baseline_run"):
                raise PipelineError("READY requires a Baseline run")
            validate_run(root, config, state, state["baseline_run"], "Baseline", require_current=False, trust_path=trust_path)
            validate_approvals(root, config, state, _roles(config, state, "design"), "design", trust_path)
        elif status in {"REVIEW", "DONE"}:
            problems = document_errors(root, state, for_done=True)
            if problems:
                raise PipelineError("; ".join(problems))
            if source_fingerprint(root, config, state) != state.get("fingerprint"):
                raise PipelineError("task fingerprint is stale")
            from .runner import validate_run, validate_completion
            summary = validate_completion(root, config, state, state["full_run"], require_current=True, trust_path=trust_path)
            _validate_acceptance(root, task_id, summary)
            if status == "DONE":
                snapshot = code_snapshot(root, config)
                _review_gate(root, config, state, trust_path, snapshot)
        if status == 'IN_PROGRESS' and state['status'] == 'REVIEW':
            # Advisory review rework needs fresh completion evidence and decisions.
            state['full_run'] = state['release_run'] = None
            state['release_status'] = 'NOT_READY'
        state["status"] = status
        state["updated_utc"] = utc_now()
        validate_schema(root, "state", state)
        write_state(root, state)
        return state


def revise_task(root: Path, task_id: str, reason: str) -> dict[str, Any]:
    if not reason.strip():
        raise PipelineError("revision reason is required")
    root = Path(root).resolve()
    with lock(root, f"task-{task_id}"):
        state = read_state(root, task_id)
        state["revision"] += 1
        state['planning_version'] = 1
        from .clarifications import template
        planning_path = safe_path(root, f'Docs/Work/{task_id}/CLARIFICATIONS.json')
        if not planning_path.exists():
            atomic_json(planning_path, template(state))
        state["status"] = "DRAFT"
        state["fingerprint"] = None
        state["approvals"] = []
        state["exceptions"] = []
        state["baseline_run"] = state["full_run"] = state["release_run"] = None
        state["release_status"] = "NOT_READY"
        state["blockers"] = [f"Revision {state['revision']}: {reason.strip()}"]
        history_path = root / "Docs" / "Work" / task_id / "REVISION_HISTORY.json"
        import json
        history = json.loads(history_path.read_text(encoding="utf-8-sig")) if history_path.is_file() else []
        history.append({"revision": state["revision"], "reason": reason.strip(), "revised_utc": utc_now()})
        atomic_json(history_path, history)
        state["updated_utc"] = utc_now()
        validate_schema(root, "state", state)
        write_state(root, state)
        return state


def archive_task(root: Path, task_id: str, trust_path: str | Path | None = None,
                 *, include_members: bool = False) -> dict[str, Any]:
    """Move validated task evidence, including an explicitly requested Phase group."""
    from .archival import archive
    return archive(root, task_id, trust_path, include_members=include_members)
