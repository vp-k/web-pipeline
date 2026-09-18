"""Safe, bounded command execution for the standalone pipeline."""

from __future__ import annotations

import json
import os
import time
import uuid
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .common import (PipelineError, atomic_json, code_snapshot, load_config,
                     lock, read_state, safe_path, source_fingerprint, utc_now,
                     validate_schema, write_state)
from .evidence import (collect_artifacts, failure_fingerprint, policy_snapshot,
                       acceptance_checks, required_checks, validate_artifact_hashes,
                       validate_screenshots)
from .budget import enforce_task, finish_run, seconds_between, task_remaining
from . import boundaries
from .test_results import validate_report
from . import scopes


PROFILES = {"Policy", "Baseline", "Fast", "Task", "Phase", "Full", "Release"}


def _validate_argv(command: dict[str, Any]) -> list[str]:
    argv = command.get("argv")
    if not isinstance(argv, list) or not argv or not all(isinstance(x, str) and x for x in argv):
        raise PipelineError(f"command {command.get('id')} must use a non-empty argv array")
    executable = argv[0].replace('\\', '/').rsplit('/', 1)[-1].lower()
    if executable.endswith('.exe'):
        executable = executable[:-4]
    lowered = [arg.lower() for arg in argv[1:]]
    forbidden = False
    if executable == 'cmd':
        forbidden = True
    elif executable in {'sh', 'bash', 'dash', 'zsh'}:
        # Only an explicit script operand. No -c, combined -lc, stdin or option forms.
        forbidden = len(argv) < 2 or argv[1].startswith('-')
    elif executable in {'powershell', 'pwsh'}:
        index = 0
        while index < len(lowered) and lowered[index] in {'-noprofile', '-noninteractive', '-nologo'}:
            index += 1
        if index < len(lowered) and lowered[index] == '-executionpolicy':
            index += 2
        forbidden = (index >= len(lowered) or lowered[index] != '-file'
                     or index + 1 >= len(lowered) or lowered[index + 1].startswith('-'))
    if forbidden:
        raise PipelineError(f"compound shell execution forbidden for {command.get('id')}; use an explicit script file")
    if command.get("environment") == "production":
        raise PipelineError(f"production command forbidden: {command.get('id')}")
    return argv


def _execute(command: dict[str, Any], root: Path, run_dir: Path,
             task_id: str | None = None, profile: str | None = None) -> dict[str, Any]:
    check_id = command["id"]
    log_rel = f"logs/{check_id}.log"
    log_path = safe_path(run_dir, log_rel)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    result = {"id": check_id, "status": "BLOCKED", "exit_code": None,
              "duration_ms": 0, "log": log_rel, "reason": None}
    try:
        argv = _validate_argv(command)
        cwd = safe_path(root, command.get("cwd", "."), must_exist=True)
        env = os.environ.copy()
        env.pop("WEB_PIPELINE_TRUST", None)
        env["PIPELINE_EVIDENCE_DIR"] = str(run_dir)
        env["PIPELINE_CHECK_ID"] = check_id
        # A timestamp/size-valid .pyc can otherwise execute old source after a
        # same-sized edit within one clock tick. Use a fresh run-local cache;
        # never delete a project's cache or silently reuse it as verification.
        env["PYTHONPYCACHEPREFIX"] = str(run_dir / '.python-cache')
        if task_id:
            env["PIPELINE_TASK_ID"] = task_id
        if profile:
            env["PIPELINE_PROFILE"] = profile
        from .process_tree import execute, wait_log_release
        with log_path.open("wb") as log:
            exit_code, reason = execute(argv, cwd, env, log,
                                        float(command.get('timeout_seconds', 300)),
                                        run_dir / f'process-{check_id}.json')
        wait_log_release(log_path)
        result.update(status='PASS' if exit_code == 0 and reason is None else 'FAIL',
                      exit_code=exit_code, reason=reason)
    except Exception as exc:
        # Even spawn and policy failures produce a durable log and summary.
        with log_path.open("ab") as log:
            log.write((f"pipeline runner error: {type(exc).__name__}: {exc}\n").encode("utf-8", "replace"))
        result["reason"] = str(exc)
    result["duration_ms"] = max(0, int((time.monotonic() - started) * 1000))
    return result


def _command_map(config: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {item["id"]: item for item in config.get("verification", {}).get("commands", [])}


def _approved_exception(root: Path, config: dict[str, Any], state: dict[str, Any],
                        check_id: str, trust_path: Path | str | None) -> dict[str, Any] | None:
    matching = False
    for rel in state.get("exceptions", []):
        try:
            record = json.loads(safe_path(root, rel, must_exist=True).read_text(encoding="utf-8-sig"))
        except (OSError, ValueError, PipelineError) as exc:
            raise PipelineError(f"invalid exception record {rel}: {exc}") from exc
        if record.get("payload", {}).get("check_id") == check_id:
            matching = True
    if not matching:
        return None
    from .approval import validate_exception
    return validate_exception(root, config, state, check_id, trust_path)


def _enforce_iteration_limits(config: dict[str, Any], state: dict[str, Any]) -> None:
    enforce_task(config, state)


def _unique_run_dir(root: Path, config: dict[str, Any], run_id: str | None) -> tuple[str, Path]:
    run_id = run_id or f"{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}-{uuid.uuid4().hex[:10]}"
    if not isinstance(run_id, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{1,63}", run_id):
        raise PipelineError("invalid run id")
    report_root = safe_path(root, config["project"]["report_root"])
    report_root.mkdir(parents=True, exist_ok=True)
    run_dir = safe_path(report_root, run_id)
    try:
        run_dir.mkdir()
    except FileExistsError as exc:
        raise PipelineError(f"run id already exists: {run_id}") from exc
    return run_id, run_dir


def _release_gate(root: Path, config: dict[str, Any], state: dict[str, Any], trust_path: Path | None) -> None:
    full_id = state.get("full_run")
    if not full_id:
        raise PipelineError("Release requires current passing completion evidence")
    validate_completion(root, config, state, full_id, require_current=True,
                 trust_path=trust_path)
    roles = {"Release Owner"}
    for protected in state.get("protected_changes", []):
        roles.update(config.get("risk", {}).get("protected_rules", {}).get(protected, {}).get("roles", []))
    try:
        from .approval import validate_approvals
    except ImportError:
        from .policy import validate_approvals  # type: ignore
    validate_approvals(root, config, state, sorted(roles), "release", trust_path=trust_path,
                       snapshot=code_snapshot(root, config), run_id=full_id)


def run_profile(root: Path | str, task_id: str, profile: str,
                trust_path: Path | str | None = None, run_id: str | None = None) -> dict[str, Any]:
    root = Path(root).resolve()
    if profile not in PROFILES:
        raise PipelineError(f"unsupported profile: {profile}")
    config = load_config(root)
    with lock(root, f"task-{task_id}"):
        state = read_state(root, task_id)
        fingerprint = source_fingerprint(root, config, state)
        if state.get("fingerprint") != fingerprint:
            raise PipelineError("task fingerprint is stale")
        if profile == 'Baseline' and state['status'] != 'DRAFT':
            raise PipelineError('Baseline is frozen after DRAFT; revise the task before recapturing it')
        if profile != "Baseline" and state.get("status") == "DRAFT":
            raise PipelineError(f"{profile} is forbidden while task is DRAFT")
        if profile in {"Fast", "Task", "Phase", "Full"} and state.get("status") not in {"IN_PROGRESS", "VERIFYING"}:
            raise PipelineError(f"{profile} requires IN_PROGRESS or VERIFYING state")
        if profile == "Release" and (state.get("risk_tier") != "T4" or state.get("status") != "DONE"):
            raise PipelineError("Release readiness requires a DONE T4 task")
        if profile in {"Policy", "Fast", "Task", "Phase", "Full", "Release"}:
            from .state import policy_check
            policy = policy_check(root, task_id=task_id, trust_path=trust_path)
            if policy["status"] != "PASS":
                raise PipelineError("policy gate failed: " + "; ".join(policy["errors"]))
        if profile in {"Fast", "Task", "Phase", "Full"}:
            _enforce_iteration_limits(config, state)
        if profile == 'Release':
            _release_gate(root, config, state, Path(trust_path) if trust_path else None)
        # Finish read-only validation and reserve a unique run before touching state.
        before_snapshot = code_snapshot(root, config)
        plan = scopes.selection(root, config, state, profile, trust_path=trust_path)
        wanted = plan['checks'] if plan else required_checks(config, state, profile, acceptance_checks(root, state))
        evidence_domains = plan['domains'] if plan else state.get('change_domains', [])
        run_id, run_dir = _unique_run_dir(root, config, run_id)
        if plan:
            atomic_json(run_dir / scopes.ARTIFACT, plan)
        started = utc_now()
        if profile in {"Fast", "Task", "Phase", "Full"}:
            iteration = state.setdefault("iteration", {})
            attempts_key = "attempts" if "attempts" in iteration else "total_attempts"
            iteration[attempts_key] = int(iteration.get(attempts_key, 0)) + 1
            iteration["started_utc"] = iteration.get("started_utc") or started
            # Reserve an unresolved (non-PASS) attempt durably before execution.
            # A conclusive PASS refunds only this reservation, never history.
            iteration['failed_attempts'] += 1
            iteration['pending_run'] = {'run_id': run_id, 'started_utc': started}
            if profile in scopes.COMPLETION:
                state["full_run"] = None
            state["updated_utc"] = utc_now()
            write_state(root, state)
        if profile == "Release":
            state["release_run"] = None
            state["release_status"] = "NOT_READY"
            state["updated_utc"] = utc_now()
            write_state(root, state)
        before_fingerprint = fingerprint
        deadline = None
        if profile in {"Fast", "Task", "Phase", "Full"}:
            deadline = time.monotonic() + max(0.0, task_remaining(config, state['iteration']) - seconds_between(started, utc_now()))
        commands = _command_map(config)
        boundary_check = config.get('boundaries', {}).get('dependency_check')
        checks: list[dict[str, Any]] = []
        patterns: list[str] = []
        try:
            for check_id in wanted:
                command = commands.get(check_id)
                if check_id == boundary_check:
                    # Engine, not adapter, owns the complete source inventory.
                    boundaries.prepare_input(root, config, run_dir, before_snapshot)
                exception = _approved_exception(root, config, state, check_id, trust_path)
                if exception:
                    checks.append({"id": check_id, "status": "NOT_APPLICABLE", "exit_code": None,
                                   "duration_ms": 0, "log": None, "reason": exception["reason"]})
                    continue
                eligible = {profile, "Policy"} | ({"Full"} if profile in {"Task", "Phase", "Release"} or plan else set())
                if not command or not command.get("enabled") or not eligible.intersection(command.get("profiles", [])):
                    reason = "missing, disabled, or not enabled for profile"
                    checks.append({"id": check_id, "status": "NOT_RUN", "exit_code": None,
                                   "duration_ms": 0, "log": None, "reason": reason})
                    continue
                executable_command = dict(command)
                budget_limited = False
                if deadline is not None:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        checks.append({"id": check_id, "status": "BLOCKED", "exit_code": None,
                                       "duration_ms": 0, "log": None,
                                       "reason": "iteration active-time limit reached", "blocker_kind": "budget"})
                        continue
                    budget_limited = remaining < float(command.get('timeout_seconds', 300))
                    executable_command["timeout_seconds"] = min(float(command.get("timeout_seconds", 300)), remaining)
                result = _execute(executable_command, root, run_dir, task_id, profile)
                if command.get('test_report') and result['status'] == 'PASS':
                    try:
                        validate_report(root, run_dir, command)
                    except (PipelineError, OSError, ValueError) as exc:
                        result.update(status='FAIL', reason=f'Test evidence invalid: {exc}')
                if check_id == boundary_check and result['status'] == 'PASS':
                    try:
                        violations = boundaries.validate_graph(root, config, run_dir, before_snapshot)
                        if violations:
                            result.update(status='FAIL', reason='; '.join(violations))
                    except (PipelineError, OSError, ValueError) as exc:
                        result.update(status='FAIL', reason=f'Boundary evidence invalid: {exc}')
                if budget_limited and result['reason'] == 'timeout':
                    result.update(status='BLOCKED', reason='iteration active-time limit reached', blocker_kind='budget')
                elif result['status'] == 'BLOCKED':
                    result['blocker_kind'] = 'external'
                checks.append(result)
                if result["status"] == "PASS":
                    patterns.extend(command.get("artifacts", []))
            if profile in {"Task", "Phase", "Full", "Release"} and "frontend" in evidence_domains:
                try:
                    validate_screenshots(root, config, run_dir)
                except PipelineError as exc:
                    exception = _approved_exception(root, config, state, "browser-screenshots", trust_path)
                    checks.append({"id": "browser-screenshots",
                                   "status": "NOT_APPLICABLE" if exception else "FAIL", "exit_code": None,
                                   "duration_ms": 0, "log": None,
                                   "reason": exception["reason"] if exception else str(exc)})
            try:
                artifacts = collect_artifacts(run_dir, patterns)
            except PipelineError as exc:
                checks.append({"id": "required-artifacts", "status": "FAIL", "exit_code": None,
                               "duration_ms": 0, "log": None, "reason": str(exc)})
                artifacts = collect_artifacts(run_dir)
            statuses = {c["status"] for c in checks}
            if checks and statuses <= {"PASS", "NOT_APPLICABLE"}:
                status = "PASS"
            elif "FAIL" in statuses:
                status = "FAIL"
            elif "BLOCKED" in statuses:
                status = "BLOCKED"
            else:
                status = "NOT_RUN"
            if (code_snapshot(root, config)["tree_digest"] != before_snapshot["tree_digest"] or
                    source_fingerprint(root, config, state) != before_fingerprint):
                checks.append({"id": "source-stability", "status": "FAIL", "exit_code": None,
                               "duration_ms": 0, "log": None, "reason": "source changed during verification"})
                status = "FAIL"
            summary = {"schema_version": "2.0", "run_id": run_id, "task_id": task_id,
                       "profile": profile, "status": status, "fingerprint": fingerprint,
                       "snapshot": before_snapshot, "policy_snapshot": policy_snapshot(config),
                       "started_utc": started, "completed_utc": utc_now(), "checks": checks,
                       "artifacts": artifacts, "failure_fingerprint": failure_fingerprint(checks, run_dir=run_dir, root=root)}
        except BaseException as exc:
            summary = {"schema_version": "2.0", "run_id": run_id, "task_id": task_id,
                       "profile": profile, "status": "FAIL", "fingerprint": fingerprint,
                       "snapshot": before_snapshot, "policy_snapshot": policy_snapshot(config),
                       "started_utc": started, "completed_utc": utc_now(),
                       "checks": checks + [{"id": "runner", "status": "BLOCKED", "exit_code": None,
                                            "duration_ms": 0, "log": None, "reason": str(exc)}],
                       "artifacts": collect_artifacts(run_dir), "failure_fingerprint": None}
            summary["failure_fingerprint"] = failure_fingerprint(summary["checks"], run_dir=run_dir, root=root)
        validate_schema(root, "pipeline-summary", summary)
        atomic_json(run_dir / "summary.json", summary)

        iteration = state.setdefault("iteration", {})
        if profile in {"Fast", "Task", "Phase", "Full"}:
            finish_run(iteration, summary)
            attempts_key = "attempts" if "attempts" in iteration else "total_attempts"
            same_key = "same_failure" 
            prior = iteration.get("last_failure") or iteration.get("last_failure_fingerprint")
            # A time-budget pause is not a new product failure and cannot clear
            # the existing same-failure guard merely by replacing its fingerprint.
            substantive = [c for c in summary['checks'] if c.get('blocker_kind') != 'budget']
            current_failure = failure_fingerprint(substantive, run_dir=run_dir, root=root)
            if current_failure or summary['status'] == 'PASS':
                iteration[same_key] = int(iteration.get(same_key, 0)) + 1 if current_failure and prior == current_failure else (1 if current_failure else 0)
                if "last_failure" in iteration:
                    iteration["last_failure"] = current_failure
                else:
                    iteration["last_failure_fingerprint"] = current_failure
            iteration["started_utc"] = iteration.get("started_utc") or started
            if any(c["status"] == "BLOCKED" and c.get('blocker_kind') != 'budget' for c in summary["checks"]):
                iteration["external_retries"] = int(iteration.get("external_retries", 0)) + 1
        baseline_captured = False
        if profile == "Baseline":
            try:
                validate_run(root, config, state, run_id, "Baseline", require_current=False,
                             trust_path=trust_path)
                baseline_captured = True
            except PipelineError:
                baseline_captured = False
        if summary["status"] == "PASS" or baseline_captured:
            pointer = {"Baseline": "baseline_run", "Task": "full_run", "Phase": "full_run", "Full": "full_run", "Release": "release_run"}.get(profile)
            if pointer:
                state[pointer] = run_id
            if profile == "Release":
                state["release_status"] = "READY"
        elif profile == "Release":
            state["release_status"] = "NOT_READY"
        state["updated_utc"] = utc_now()
        write_state(root, state)
        return summary


def validate_run(root: Path | str, config: dict[str, Any], state: dict[str, Any], run_id: str,
                 profile: str | None = None, require_current: bool = True,
                 trust_path: Path | str | None = None) -> dict[str, Any]:
    root = Path(root).resolve()
    run_dir = safe_path(safe_path(root, config["project"]["report_root"], must_exist=True), run_id, must_exist=True)
    summary_path = safe_path(run_dir, "summary.json", must_exist=True)
    try:
        summary = json.loads(summary_path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PipelineError(f"invalid run summary: {exc}") from exc
    validate_schema(root, "pipeline-summary", summary)
    if summary.get("run_id") != run_id or summary.get("task_id") != state.get("task_id"):
        raise PipelineError("run identity mismatch")
    if profile and summary.get("profile") != profile:
        raise PipelineError("run profile mismatch")
    baseline_capture = summary.get("profile") == "Baseline"
    if summary.get("status") != "PASS" and not (baseline_capture and summary.get("status") == "FAIL"):
        raise PipelineError("run is not passing")
    if summary.get("policy_snapshot") != policy_snapshot(config):
        raise PipelineError("verification policy changed since run")
    current_fingerprint = source_fingerprint(root, config, state)
    if summary.get("fingerprint") != current_fingerprint:
        raise PipelineError("run task/source fingerprint is stale")
    if require_current and summary.get("snapshot", {}).get("tree_digest") != code_snapshot(root, config)["tree_digest"]:
        raise PipelineError("run code snapshot is stale")
    checks = summary.get("checks", [])
    by_id = {c.get("id"): c for c in checks}
    if len(by_id) != len(checks):
        raise PipelineError("duplicate check ids in summary")
    selected_profile = summary.get("profile")
    boundary_check = config.get('boundaries', {}).get('dependency_check')
    policy_ids = set(config.get("verification", {}).get("policy_checks", []))
    plan = None
    if scopes.enabled(config):
        plan_path = safe_path(run_dir, scopes.ARTIFACT, True)
        plan = json.loads(plan_path.read_text(encoding='utf-8-sig'))
        validate_schema(root, 'verification-selection', plan)
        expected = scopes.selection(root, config, state, selected_profile,
                                    changed_paths=None if require_current else plan.get('changed_paths'),
                                    trust_path=trust_path)
        if plan != expected:
            raise PipelineError('Verification scope changed or selection evidence is invalid')
        if scopes.ARTIFACT not in {a['path'] for a in summary.get('artifacts', [])}:
            raise PipelineError('Verification scope evidence is not hash-bound')
    wanted = plan['checks'] if plan else required_checks(config, state, selected_profile, acceptance_checks(root, state))
    for check_id in wanted:
        status = by_id.get(check_id, {}).get("status")
        allowed = {"PASS", "NOT_APPLICABLE"} | ({"FAIL"} if baseline_capture and check_id not in policy_ids else set())
        if status not in allowed:
            raise PipelineError(f"required check did not pass: {check_id}")
    for check in checks:
        if check.get("status") == "NOT_APPLICABLE":
            from .approval import validate_exception
            validate_exception(root, config, state, check["id"], trust_path)
        elif baseline_capture and check.get("status") == "FAIL" and check.get("id") not in policy_ids:
            semantic_boundary_failure = check['id'] == boundary_check and check.get('exit_code') == 0
            if not isinstance(check.get("exit_code"), int) or (check["exit_code"] == 0 and not semantic_boundary_failure) or not check.get("log"):
                raise PipelineError(f"Baseline failure lacks executed nonzero exit/log evidence: {check['id']}")
        elif check.get("status") != "PASS":
            raise PipelineError("run contains a non-passing check")
        elif check.get("exit_code") != 0 or not check.get("log"):
            raise PipelineError(f"executed PASS lacks exit code/log evidence: {check['id']}")
    validate_artifact_hashes(run_dir, summary.get("artifacts", []))
    recorded = {a["path"] for a in summary.get("artifacts", [])}
    if boundary_check and by_id[boundary_check]['status'] != 'NOT_APPLICABLE':
        if not {boundaries.INPUT, boundaries.GRAPH} <= recorded:
            raise PipelineError('Boundary input/graph evidence is not hash-bound')
        violations = boundaries.validate_graph(root, config, run_dir, summary['snapshot'], require_current)
        if violations and not (baseline_capture and by_id[boundary_check]['status'] == 'FAIL'):
            raise PipelineError('Boundary violations: ' + '; '.join(violations))
        if not violations and by_id[boundary_check]['status'] == 'FAIL' and by_id[boundary_check]['exit_code'] == 0:
            raise PipelineError('Boundary Baseline FAIL has no conclusive violation evidence')
    for check in checks:
        if check.get("log") and check["log"] not in recorded:
            raise PipelineError(f"check log is not hash-bound: {check['id']}")
    commands = _command_map(config)
    for check_id in wanted:
        command = commands.get(check_id, {})
        check = by_id[check_id]
        if command.get('test_report') and check['status'] != 'NOT_APPLICABLE':
            if command['test_report']['path'] not in recorded:
                raise PipelineError(f'Test report is not hash-bound: {check_id}')
            counts = validate_report(root, run_dir, command, allow_failures=baseline_capture and check['status'] == 'FAIL')
            if check['status'] == 'FAIL' and counts['failures'] == 0:
                raise PipelineError('Baseline test FAIL has no failed test evidence')
        if by_id[check_id]["status"] != "PASS":
            continue
        for pattern in commands.get(check_id, {}).get("artifacts", []):
            matches = {p.relative_to(run_dir).as_posix() for p in run_dir.glob(pattern) if p.is_file()}
            if not matches or not matches.issubset(recorded):
                raise PipelineError(f"required artifacts are not hash-bound: {check_id}")
    if selected_profile in {"Task", "Phase", "Full", "Release"} and "frontend" in (plan["domains"] if plan else state.get("change_domains", [])):
        screenshot_check = by_id.get("browser-screenshots")
        if screenshot_check and screenshot_check.get("status") == "NOT_APPLICABLE":
            from .approval import validate_exception
            validate_exception(root, config, state, "browser-screenshots", trust_path)
        else:
            screenshot_paths = validate_screenshots(root, config, run_dir)
            if not set(screenshot_paths).issubset(recorded) or "screenshots/manifest.json" not in recorded:
                raise PipelineError("screenshot evidence is not hash-bound")
    return summary


def validate_completion(root, config, state, run_id, require_current=True, trust_path=None):
    """Validate the configured completion profile; explicit Full is a stronger run."""
    expected = scopes.completion_profile(root, config, state)
    summary = validate_run(root, config, state, run_id, require_current=require_current, trust_path=trust_path)
    if summary['profile'] not in {expected, 'Full'}:
        raise PipelineError(f'Completion requires {expected} or Full evidence')
    return summary
