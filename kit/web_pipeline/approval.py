from __future__ import annotations

import base64
import json
import os
from pathlib import Path
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from .common import PipelineError, hash_file, parse_time, safe_path, utc_now, validate_schema


def _trust(root: Path, trust_path: str | Path | None) -> dict[str, Any]:
    raw = trust_path or os.environ.get("WEB_PIPELINE_TRUST")
    if not raw:
        raise PipelineError("an external trust file is required (--trust or WEB_PIPELINE_TRUST)")
    path = Path(raw).expanduser().resolve()
    project = Path(root).resolve()
    try:
        path.relative_to(project)
    except ValueError:
        pass
    else:
        raise PipelineError("trust file must be outside the project")
    if not path.is_file():
        raise PipelineError(f"trust file does not exist: {path}")
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    validate_schema(Path(root), "trust", data)
    try:
        public_keys = [base64.b64decode(item['public_key'], validate=True) for item in data['identities'].values()]
        if any(len(key) != 32 for key in public_keys):
            raise ValueError('Ed25519 public key length')
    except ValueError as exc:
        raise PipelineError('Trust contains an invalid Ed25519 public key') from exc
    if len(public_keys) != len(set(public_keys)):
        raise PipelineError('Each human identity must use a distinct approval public key')
    return data


def _verify_record(root: Path, state: dict[str, Any], rel: str, trust: dict[str, Any],
                   phase: str, snapshot: dict[str, Any] | None, run_id: str | None) -> dict[str, Any]:
    path = safe_path(Path(root), rel, must_exist=True)
    record = json.loads(path.read_text(encoding="utf-8-sig"))
    validate_schema(Path(root), "exception" if phase == "exception" else "approval", record)
    payload = record["payload"]
    identity = trust["identities"].get(payload["identity"])
    if not identity or identity.get("type") != "human":
        raise PipelineError(f"approval identity is not a trusted human: {payload['identity']}")
    if payload["role"] not in identity.get("roles", []):
        raise PipelineError(f"identity {payload['identity']} is not trusted for exact role {payload['role']}")
    message = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    try:
        key = Ed25519PublicKey.from_public_bytes(base64.b64decode(identity["public_key"], validate=True))
        key.verify(base64.b64decode(record["signature"], validate=True), message)
    except (ValueError, InvalidSignature) as exc:
        raise PipelineError(f"invalid approval signature: {rel}") from exc
    now = parse_time(utc_now())
    if parse_time(payload["approved_utc"]) > now or parse_time(payload["expires_utc"]) <= now:
        raise PipelineError(f"approval is not currently valid: {rel}")
    _validate_binding(root, state, payload, phase, snapshot, run_id, rel)
    return payload


def _validate_binding(root, state, payload, phase, snapshot, run_id, rel):
    if payload["task_id"] != state["task_id"] or payload["revision"] != state["revision"]:
        raise PipelineError(f"stale or mismatched approval: {rel}")
    if payload["fingerprint"] != state.get("fingerprint"):
        raise PipelineError(f"approval fingerprint is stale: {rel}")
    if payload["phase"] != phase or payload.get("outcome") != "APPROVED":
        raise PipelineError(f"approval phase/outcome mismatch: {rel}")
    if phase in {"review", "release"}:
        if not snapshot or payload.get("tree_digest") != snapshot.get("tree_digest"):
            raise PipelineError(f"approval does not bind the current tree: {rel}")
        if not run_id or payload.get("run_id") != run_id:
            raise PipelineError(f"approval does not bind the required run: {rel}")
    for condition in payload.get("conditions", []):
        if condition.get("status") != "PASS":
            raise PipelineError(f"approval condition is not PASS: {rel}")
        evidence = safe_path(Path(root), condition["evidence"], must_exist=True)
        if hash_file(evidence) != condition["sha256"]:
            raise PipelineError(f"approval condition evidence hash mismatch: {rel}")


def _verify_any(root, config, state, rel, trust_path, phase, snapshot=None, run_id=None):
    record = json.loads(safe_path(root, rel, must_exist=True).read_text(encoding='utf-8-sig'))
    if record.get('kind') == 'user_approval':
        from .user_approval import verify_receipt
        return verify_receipt(root, config, state, record, phase, snapshot, run_id)
    return _verify_record(root, state, rel, _trust(root, trust_path), phase, snapshot, run_id)


def _payload_roles(payload):
    return payload.get('roles', [payload.get('role')])


def validate_approvals(root: Path, config: dict[str, Any], state: dict[str, Any], roles: list[str],
                       phase: str, trust_path: str | Path | None = None,
                       snapshot: dict[str, Any] | None = None, run_id: str | None = None) -> None:
    if not roles:
        return
    if config.get('approval_policy', 'strict') != 'standard':
        _trust(Path(root), trust_path)
    records = state.get("exceptions", []) if phase == "exception" else state.get("approvals", [])
    valid: dict[str, list[dict[str, Any]]] = {role: [] for role in roles}
    failures: list[str] = []
    for rel in records:
        try:
            payload = _verify_any(Path(root), config, state, rel, trust_path, phase, snapshot, run_id)
            if phase in {"review", "release"}:
                summary = safe_path(Path(root), f"{config['project']['report_root'].rstrip('/')}/{run_id}/summary.json",
                                    must_exist=True)
                if payload.get("run_digest") != hash_file(summary):
                    raise PipelineError(f"approval does not bind the run summary bytes: {rel}")
            for role in _payload_roles(payload):
                if role in valid:
                    valid[role].append(payload)
        except (PipelineError, OSError, ValueError, KeyError) as exc:
            failures.append(str(exc))
    for role, payloads in valid.items():
        if not payloads:
            detail = f" ({'; '.join(failures)})" if failures else ""
            if config.get('approval_policy') == 'standard':
                detail += ' Use approval-request/approve for explicit user consent; user receipts need no identity or trust file.'
            raise PipelineError(f"missing valid {phase} approval for exact role {role}{detail}")
        if role == "Reviewer" and state.get("implementer") and all(
                p.get("identity") == state["implementer"] for p in payloads):
            raise PipelineError("Reviewer must be independent from the implementer")
        if phase in {"design", "release"}:
            role_scope = {change for change in state.get("protected_changes", [])
                          if role in config["risk"]["protected_rules"][change].get("roles", [])}
            if role == "Release Owner":
                role_scope = set(state.get("protected_changes", []))
            covered_by_role = {item for p in payloads for item in p.get("scope", [])}
            if role_scope - covered_by_role:
                raise PipelineError(
                    f"{role} approval scope does not cover: {sorted(role_scope - covered_by_role)}")
    if phase in {"design", "release"}:
        required_scope = set(state.get("protected_changes", []))
        covered = {item for payloads in valid.values() for p in payloads for item in p.get("scope", [])}
        if required_scope - covered:
            raise PipelineError(f"approval scope does not cover protected changes: {sorted(required_scope - covered)}")
    if phase == "release" and state.get("risk_tier") == "T4":
        payloads = [p for group in valid.values() for p in group]
        local_user_decision = config.get('approval_policy') == 'standard' and any('roles' in p for p in payloads)
        identities = {p['identity'] for p in payloads if 'identity' in p}
        if not local_user_decision and (len(identities) < 2 or state.get("implementer") in identities):
            raise PipelineError("T4 release requires at least two human approvers distinct from implementer")


def validate_exception(root: Path, config: dict[str, Any], state: dict[str, Any], check_id: str,
                       trust_path: str | Path | None = None) -> dict[str, Any]:
    """Validate a check-specific user decision; exceptions never manufacture PASS."""
    relevant = {change for change in state.get("protected_changes", [])
                if any(check_id in ids for ids in config["risk"]["protected_rules"][change]
                       .get("checks", {}).values())}
    roles = {"Tech Owner"}
    for change in relevant:
        roles.update(config["risk"]["protected_rules"][change].get("roles", []))
    matching: list[str] = []
    for rel in state.get("exceptions", []):
        try:
            record = json.loads(safe_path(Path(root), rel, must_exist=True).read_text(encoding="utf-8-sig"))
            if record.get("payload", {}).get("check_id") == check_id:
                matching.append(rel)
        except (OSError, ValueError, PipelineError):
            continue
    candidate = dict(state)
    candidate["exceptions"] = matching
    validate_approvals(root, config, candidate, sorted(roles), "exception", trust_path)
    payloads = []
    for rel in matching:
        try:
            payloads.append(_verify_any(Path(root), config, state, rel, trust_path, 'exception'))
        except (PipelineError, OSError, ValueError, KeyError):
            continue  # Invalid historical candidates never cover a required role.
    covered = {scope for payload in payloads for scope in payload.get("scope", [])}
    if relevant - covered:
        raise PipelineError(f"exception scope does not cover protected checks: {sorted(relevant - covered)}")
    for role in roles:
        role_scope = {change for change in relevant
                      if role in config['risk']['protected_rules'][change]['roles']}
        covered_by_role = {scope for payload in payloads if role in _payload_roles(payload)
                           for scope in payload.get('scope', [])}
        if role_scope - covered_by_role:
            raise PipelineError(f'{role} exception must explicitly cover its protected scope')
    if not all(payload.get("reason") for payload in payloads):
        raise PipelineError("exception reason is required")
    return payloads[0]
