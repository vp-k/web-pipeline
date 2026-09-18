from __future__ import annotations

import fnmatch
import re
import subprocess
from pathlib import Path
from typing import Any

from .common import PipelineError, output_exclusions, safe_path, validate_schema

TIERS = ("T0", "T1", "T2", "T3", "T4")
MIGRATION_FLOORS = {
    "none": "T0", "reversible": "T2", "backward_compatible": "T3",
    "destructive": "T4", "irreversible": "T4",
}


def _max_tier(*tiers: str) -> str:
    try:
        return max(tiers, key=TIERS.index)
    except (ValueError, TypeError) as exc:
        raise PipelineError(f"invalid risk tier: {tiers}") from exc


def option_shaped(ref: str | None) -> bool:
    """A base_ref that git would parse as an option instead of a revision."""
    return ref is not None and ref.strip().startswith("-")


def _changed_paths(root: Path, base_ref: str | None) -> tuple[list[str], list[str]]:
    if not base_ref:
        return [], []
    if option_shaped(base_ref):
        return [], [f"base_ref {base_ref!r} must be a git revision, not an option"]
    # Renames affect both the old owner and the destination's consumers.
    commands = (["git", "diff", "--no-renames", "--name-only", "-z", "--diff-filter=ACDMRTUXB", f"{base_ref}...HEAD"],
                ["git", "diff", "--no-renames", "--name-only", "-z", "--cached", "--diff-filter=ACDMRTUXB"],
                ["git", "diff", "--no-renames", "--name-only", "-z", "--diff-filter=ACDMRTUXB"])
    paths: set[str] = set()
    for command in commands:
        result = subprocess.run(command, cwd=root, capture_output=True, check=False, timeout=120)
        if result.returncode:
            detail = result.stderr.decode(errors="replace").strip() or "git diff failed"
            return [], [f"cannot inspect diff from base_ref {base_ref!r}: {detail}"]
        paths.update(p.decode("utf-8", errors="surrogateescape").replace("\\", "/")
                     for p in result.stdout.split(b"\0") if p)
    untracked = subprocess.run(["git", "ls-files", "--others", "--exclude-standard", "-z"],
                               cwd=root, capture_output=True, check=False, timeout=120)
    if untracked.returncode:
        return [], [f"cannot inspect untracked files: {untracked.stderr.decode(errors='replace').strip()}"]
    paths.update(p.decode("utf-8", errors="surrogateescape").replace("\\", "/")
                 for p in untracked.stdout.split(b"\0") if p)
    return sorted(paths), []


def classify(root: Path, config: dict[str, Any], state: dict[str, Any], *, changed_paths=None) -> dict[str, Any]:
    """Compute a monotonic classification. Path rules are conservative hints, not semantic proof."""
    root = Path(root).resolve()
    domains = set(state.get("change_domains", []))
    protected = set(state.get("protected_changes", []))
    tier = state.get("requested_tier", "T0")
    warnings: list[str] = []
    errors: list[str] = []
    paths, diff_errors = _changed_paths(root, state.get("base_ref")) if changed_paths is None else (changed_paths, [])
    report, generated_paths = output_exclusions(root, config)
    report_root = report + '/'
    generated = tuple(path.rstrip("/") + "/" for path in generated_paths)
    paths = [path for path in paths if not (
        path.startswith(".pipeline-locks/") or path.startswith("Docs/Work/") or path.startswith('Docs/Archive/') or path.startswith(report_root)
        or path.startswith(generated) or any(part in {"node_modules", "__pycache__", ".pytest_cache"}
                                              for part in path.split("/"))
    )]
    errors.extend(diff_errors)
    from .boundaries import classify_paths
    try:
        domains.update(classify_paths(config, paths))
    except PipelineError as exc:
        errors.append(str(exc))
    from .scopes import classification
    try:
        scoped_domains, scoped_protected, scoped_tier = classification(root, config, state, paths)
        domains.update(scoped_domains)
        protected.update(scoped_protected)
        tier = _max_tier(tier, scoped_tier)
    except (PipelineError, OSError, ValueError) as exc:
        errors.append(str(exc))
    risk = config["risk"]
    for path in paths:
        for rule in risk.get("path_rules", []):
            if fnmatch.fnmatchcase(path, rule["pattern"]):
                domains.update(rule.get("domains", []))
                protected.update(rule.get("protected_changes", []))
                tier = _max_tier(tier, rule.get("tier", "T0"))
    migration = state.get("migration_class", "none")
    if migration not in MIGRATION_FLOORS:
        errors.append(f"unknown migration class: {migration}")
    else:
        tier = _max_tier(tier, MIGRATION_FLOORS[migration])
    if migration in {"reversible", "backward_compatible", "destructive", "irreversible"}:
        protected.add("database_schema")
    if migration in {"destructive", "irreversible"}:
        protected.add("destructive_migration")
    # Close domain <-> protected implications to a fixed point.
    while True:
        before = (len(domains), len(protected))
        for domain in tuple(domains):
            floor = risk.get("domain_floor", {}).get(domain)
            if floor is None:
                errors.append(f"unknown or unclassified domain: {domain}")
            else:
                tier = _max_tier(tier, floor)
                protected.update(risk.get("domain_protected_map", {}).get(domain, []))
        for change in tuple(protected):
            rule = risk.get("protected_rules", {}).get(change)
            if rule is None:
                errors.append(f"protected change has no configured rule: {change}")
            else:
                tier = _max_tier(tier, rule["tier"])
                domains.update(rule.get("domains", []))
        if before == (len(domains), len(protected)):
            break
    if paths:
        warnings.append("path rules only promote classification; semantic review is still required")
    return {"risk_tier": tier, "change_domains": sorted(domains),
            "protected_changes": sorted(protected), "changed_paths": paths,
            "errors": errors, "warnings": warnings}


def document_errors(root: Path, state: dict[str, Any], *, for_done: bool = False) -> list[str]:
    task_dir = Path(root) / "Docs" / "Work" / state["task_id"]
    errors: list[str] = []
    required = ["BRIEF.md", "DOR.md", "ACCEPTANCE.json"]
    from .clarifications import errors as planning_errors
    errors.extend(planning_errors(root, state))
    tier = TIERS.index(state["risk_tier"])
    if tier >= 2:
        required.append("PLAN.md")
    if tier >= 3:
        required.append("EXEC_PLAN.md")
    if tier >= 4:
        required.append("RELEASE.md")
    for name in required:
        path = task_dir / name
        if not path.is_file() or not path.read_text(encoding="utf-8-sig").strip():
            errors.append(f"missing or empty required task document: {name}")
        elif name.endswith('.md') and re.search(r'(?im)^\s*(?:TBD|TODO|UNSET)\s*$', path.read_text(encoding='utf-8-sig')):
            errors.append(f"unfilled template placeholder in required task document: {name}")
    acceptance = task_dir / "ACCEPTANCE.json"
    if acceptance.is_file():
        import json
        try:
            data = json.loads(acceptance.read_text(encoding="utf-8-sig"))
            validate_schema(Path(root), "acceptance", data)
            criteria = data.get("criteria") if isinstance(data, dict) else None
            if not criteria or any(not c.get("id") or not c.get("description") or not c.get("checks") for c in criteria):
                errors.append("ACCEPTANCE.json must contain populated criteria with checks")
            elif len({c['id'] for c in criteria}) != len(criteria):
                errors.append('Acceptance criterion IDs must be unique')
        except (ValueError, OSError) as exc:
            errors.append(f"invalid ACCEPTANCE.json: {exc}")
    for rel in state.get("decision_records", []):
        try:
            data_path = safe_path(Path(root), rel, must_exist=True)
            import json
            record = json.loads(data_path.read_text(encoding="utf-8-sig"))
            validate_schema(Path(root), "adr", record)
            if record["task_id"] != state["task_id"] or record["revision"] != state["revision"]:
                errors.append(f"stale or mismatched ADR: {rel}")
            if record["status"] != "ACCEPTED":
                errors.append(f"ADR is not ACCEPTED: {rel}")
        except (PipelineError, OSError, ValueError, KeyError) as exc:
            errors.append(f"invalid ADR {rel}: {exc}")
    if tier >= 3 and not state.get("decision_records"):
        errors.append("T3/T4 task requires an accepted ADR")
    if state.get("protected_changes"):
        covered: set[str] = set()
        for rel in state.get("decision_records", []):
            try:
                import json
                covered.update(json.loads(safe_path(Path(root), rel, True).read_text(encoding="utf-8-sig"))["scope"])
            except Exception:
                pass
        missing = set(state["protected_changes"]) - covered
        if missing:
            errors.append(f"protected scope lacks an accepted ADR: {sorted(missing)}")
    if for_done and not state.get("full_run"):
        errors.append("DONE requires a current completion run")
    return errors
