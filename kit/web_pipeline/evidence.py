"""Creation and validation helpers for immutable pipeline run evidence."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Iterable

from .common import PipelineError, canonical_hash, hash_file, safe_path, validate_schema


PASS = "PASS"
NON_PASSING = {"FAIL", "NOT_RUN", "BLOCKED", "NOT_APPLICABLE", "INCONCLUSIVE"}


def policy_snapshot(config: dict[str, Any]) -> str:
    """Bind a run to all configuration which determines its verdict."""
    policy = {
        "risk": config.get("risk", {}),
        "verification": config.get("verification", {}),
        "evidence": config.get("evidence", {}),
        "iteration_limits": config.get("iteration_limits", {}),
    }
    if 'boundaries' in config:
        policy['boundaries'] = config['boundaries']
    return canonical_hash(policy)


def acceptance_checks(root: Path, state: dict[str, Any]) -> list[str]:
    path = safe_path(root, f"Docs/Work/{state['task_id']}/ACCEPTANCE.json", True)
    data = json.loads(path.read_text(encoding='utf-8-sig'))
    validate_schema(root, 'acceptance', data)
    return sorted({check for criterion in data['criteria'] for check in criterion['checks']})


def required_checks(config: dict[str, Any], state: dict[str, Any], profile: str,
                    task_checks: Iterable[str] = ()) -> list[str]:
    if profile not in {"Policy", "Baseline", "Fast", "Full", "Release"}:
        raise PipelineError(f"unsupported profile: {profile}")
    requirements = config.get("verification", {}).get("requirements", {})
    wanted: set[str] = set(config.get("verification", {}).get("policy_checks", []))
    if profile in {'Full', 'Release'}:
        wanted.update(task_checks)
    profiles = [profile]
    if profile == "Release":
        profiles.insert(0, "Full")
    for domain in state.get("change_domains", []):
        domain_profiles = requirements.get(domain, {})
        for selected in profiles:
            wanted.update(domain_profiles.get(selected, []))
    rules = config.get("risk", {}).get("protected_rules", {})
    for protected in state.get("protected_changes", []):
        rule = rules.get(protected, {})
        for selected in profiles:
            wanted.update(rule.get("checks", {}).get(selected, []))
    from .boundaries import required_checks as boundary_checks
    wanted.update(boundary_checks(config, profile))
    return sorted(wanted)


def collect_artifacts(run_dir: Path, patterns: Iterable[str] = ()) -> list[dict[str, Any]]:
    """Hash evidence files and enforce configured run-relative artifact globs."""
    files: dict[str, Path] = {}
    for pattern in patterns:
        if Path(pattern).is_absolute() or ".." in Path(pattern).parts:
            raise PipelineError(f"unsafe artifact pattern: {pattern}")
        matches = [p for p in run_dir.glob(pattern) if p.is_file()]
        if not matches:
            raise PipelineError(f"required artifact missing: {pattern}")
        for path in matches:
            files[path.relative_to(run_dir).as_posix()] = path
    # Logs and screenshots are evidence even when not declared as command outputs.
    for folder in ("logs", "screenshots", "junit", "artifacts"):
        base = run_dir / folder
        if base.exists():
            for path in base.rglob("*"):
                if path.is_file():
                    files[path.relative_to(run_dir).as_posix()] = path
    return [
        {"path": rel, "size": safe_path(run_dir, rel, True).stat().st_size,
         "sha256": hash_file(safe_path(run_dir, rel, True))}
        for rel, path in sorted(files.items())
    ]


def validate_screenshots(root: Path, config: dict[str, Any], run_dir: Path) -> list[str]:
    manifest_path = safe_path(run_dir, 'screenshots/manifest.json')
    if not manifest_path.is_file():
        raise PipelineError("frontend completion/Release requires screenshots/manifest.json")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PipelineError(f"invalid screenshot manifest: {exc}") from exc
    if not isinstance(manifest, list):
        raise PipelineError("screenshot manifest must be an array")
    expected = config.get("evidence", {})
    seen: set[str] = set()
    paths: list[str] = []
    try:
        from PIL import Image
    except ImportError as exc:  # pragma: no cover - installation error
        raise PipelineError("Pillow is required to validate screenshot evidence") from exc
    for item in manifest:
        if not isinstance(item, dict) or item.get("kind") not in {"desktop", "mobile"}:
            raise PipelineError("invalid screenshot manifest entry")
        kind = item["kind"]
        rel = item.get("path")
        if not isinstance(rel, str) or not rel.startswith("screenshots/"):
            raise PipelineError("screenshot path must be run-relative under screenshots/")
        image_path = safe_path(run_dir, rel, must_exist=True)
        dims = expected.get(kind, {})
        width, height = int(item.get("width", -1)), int(item.get("height", -1))
        if (width, height) != (dims.get("width"), dims.get("height")):
            raise PipelineError(f"wrong declared {kind} screenshot dimensions")
        try:
            with Image.open(image_path) as image:
                image.verify()
            with Image.open(image_path) as image:
                actual = image.size
        except Exception as exc:
            raise PipelineError(f"screenshot is not a decodable image: {rel}") from exc
        if actual != (width, height):
            raise PipelineError(f"wrong decoded screenshot dimensions: {rel}")
        if not isinstance(item.get("url"), str) or not item["url"]:
            raise PipelineError(f"screenshot URL missing: {rel}")
        seen.add(kind)
        paths.append(rel)
    if seen != {"desktop", "mobile"}:
        raise PipelineError("both desktop and mobile screenshots are required")
    return paths


def _failure_diagnostic(path: Path, run_dir: Path, root: Path | None) -> str:
    # Bound memory, retain the error tail, and exclude routine progress output
    # when an error/test identity is available. Raw logs remain immutable evidence.
    with path.open('rb') as stream:
        stream.seek(max(0, path.stat().st_size - 1024 * 1024))
        content = stream.read().decode('utf-8', 'replace')
    content = re.sub(r'\x1b\[[0-?]*[ -/]*[@-~]', '', content)
    for directory, replacement in ((run_dir, '<run>'), (root, '<root>')):
        if directory:
            for spelling in (str(directory.resolve()), directory.resolve().as_posix()):
                content = content.replace(spelling, replacement)
    lines = content.splitlines()
    errors = [line for line in lines if re.search(
        r'(?i)(\b(?:fail(?:ed|ure)?|error|panic|exception)\b|\b\w*(?:Error|Exception)\b)', line)]
    content = '\n'.join(errors or lines)
    content = re.sub(r'\b\d{4}-\d\d-\d\d[T ]\d\d:\d\d:\d\d(?:\.\d+)?(?:Z|[+-]\d\d:\d\d)?', '<time>', content)
    content = re.sub(r'\b\d+(?:\.\d+)?\s*(?:ms|seconds?|secs?)\b', '<duration>', content)
    content = re.sub(r'\b0x[0-9a-fA-F]+\b', '<address>', content)
    content = re.sub(r'(?i)\bpid[=: ]+\d+', 'pid=<pid>', content)
    return canonical_hash(content.strip())


def failure_fingerprint(checks: list[dict[str, Any]], *, run_dir: Path | None = None,
                        root: Path | None = None) -> str | None:
    failures = []
    for check in sorted(checks, key=lambda item: item['id']):
        if check['status'] in {PASS, 'NOT_APPLICABLE'}:
            continue
        failure = {key: check.get(key) for key in ('id', 'status', 'exit_code', 'reason')}
        if run_dir is not None and check.get('log'):
            path = safe_path(run_dir, check['log'])
            if path.is_file():
                failure['diagnostic'] = _failure_diagnostic(path, run_dir, root)
        failures.append(failure)
    return canonical_hash(failures) if failures else None


def validate_artifact_hashes(run_dir: Path, artifacts: list[dict[str, Any]]) -> None:
    seen: set[str] = set()
    for artifact in artifacts:
        rel = artifact.get("path")
        if not isinstance(rel, str) or rel in seen:
            raise PipelineError("invalid or duplicate artifact path")
        seen.add(rel)
        path = safe_path(run_dir, rel, must_exist=True)
        if path.stat().st_size != artifact.get("size") or hash_file(path) != artifact.get("sha256"):
            raise PipelineError(f"artifact integrity failure: {rel}")
