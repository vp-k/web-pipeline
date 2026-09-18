"""Command-line interface for the standalone web pipeline."""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path
from typing import Any

from .common import PipelineError, load_config, read_state, source_fingerprint


def _csv(value: str | None) -> list[str]:
    return [item.strip() for item in (value or "").split(",") if item.strip()]


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="web-pipeline")
    parser.add_argument("--root", default=".", help="project root (default: current directory)")
    commands = parser.add_subparsers(dest="command", required=True)
    validate = commands.add_parser("validate")
    validate.add_argument("--kit", action="store_true")
    validate.add_argument("--task")
    validate.add_argument("--base-ref")
    validate.add_argument("--trust")
    validate.add_argument('--gate', choices=['progress', 'merge'], default='progress')
    new = commands.add_parser("new")
    new.add_argument("--task", required=True); new.add_argument("--title", required=True)
    new.add_argument("--tier", choices=[f"T{i}" for i in range(5)], default="T1")
    new.add_argument("--domains", required=True); new.add_argument("--protected", default="")
    new.add_argument("--migration", default="none", choices=["none", "reversible", "backward_compatible", "destructive", "irreversible"])
    new.add_argument("--base-ref")
    transition = commands.add_parser("transition")
    transition.add_argument("--task", required=True); transition.add_argument("--status", required=True, choices=["DRAFT","READY","IN_PROGRESS","VERIFYING","REVIEW","DONE","BLOCKED"])
    transition.add_argument("--trust")
    prepare = commands.add_parser("prepare")
    prepare.add_argument("--task", required=True); prepare.add_argument("--implementer", default='claude', help='execution label, not a human identity (default: claude)')
    clarification = commands.add_parser('clarification-report', help='read-only planning questions; CLEAR is not readiness or approval')
    clarification.add_argument('--task', required=True)
    review = commands.add_parser('review', help='record local self-review for standard unprotected T1/T2; not human approval')
    review.add_argument('--task', required=True)
    review.add_argument('--decision', required=True)
    request = commands.add_parser('approval-request', help='show source-bound scope for a standard user decision; grants no approval')
    request.add_argument('--task', required=True)
    request.add_argument('--phase', required=True, choices=['design', 'review', 'release', 'exception'])
    request.add_argument('--check-id')
    request.add_argument('--trust', help='external trust file for existing signed records; unnecessary for user receipts')
    approve = commands.add_parser('approve', help='record explicit user consent in standard; not a signature or production authority')
    approve.add_argument('--task', required=True)
    approve.add_argument('--record', required=True)
    approve.add_argument('--trust', help='external trust for signed prerequisite evidence; unnecessary for user receipts alone')
    attach = commands.add_parser("attach", help="register a record, without granting approval")
    attach.add_argument("--task", required=True)
    attach.add_argument("--kind", required=True, choices=["adr", "approval", "exception"])
    attach.add_argument("--path", required=True)
    archive = commands.add_parser('archive', help='preserve validated DONE task as historical evidence')
    archive_target = archive.add_mutually_exclusive_group(required=True)
    archive_target.add_argument('--task')
    archive_target.add_argument('--recover', action='store_true')
    archive.add_argument('--include-members', action='store_true')
    archive.add_argument('--trust')
    revise = commands.add_parser("revise")
    revise.add_argument("--task", required=True); revise.add_argument("--reason", required=True)
    run = commands.add_parser("run")
    run.add_argument("--task", required=True); run.add_argument("--profile", required=True, choices=["Policy","Baseline","Fast","Task","Phase","Full","Release"])
    run.add_argument("--run-id"); run.add_argument("--trust")
    plan = commands.add_parser('verification-plan', help='inspect selected checks and scope without execution')
    plan.add_argument('--task', required=True)
    plan.add_argument('--profile', choices=['Policy', 'Baseline', 'Fast', 'Task', 'Phase', 'Full', 'Release'])
    plan.add_argument('--trust')
    fingerprint = commands.add_parser("fingerprint"); fingerprint.add_argument("--task", required=True)
    init = commands.add_parser("init"); init.add_argument("--target", required=True)
    init.add_argument('--preview', action='store_true', help='list conflicts without writes')
    init.add_argument('--domains', help='comma-separated supported domains (default: all)')
    init.add_argument('--ci', action='store_true', help='also write .github/workflows/project-policy.yml')
    status = commands.add_parser('status', help='read-only summary: readiness, tasks, locks, queue and next step')
    status.add_argument('--task')
    locks = commands.add_parser('locks', help='list operation locks; --clear-stale removes those whose process is gone')
    locks.add_argument('--clear-stale', action='store_true')
    inspect = commands.add_parser('inspect', help='read-only project/tooling diagnosis')
    inspect.add_argument('--target', required=True)
    upgrade = commands.add_parser('upgrade', help='managed engine preview; --apply explicitly writes with backup')
    upgrade.add_argument('--target', required=True)
    upgrade.add_argument('--baseline')
    upgrade.add_argument('--apply', action='store_true')
    restore = commands.add_parser('restore', help='restore an explicit engine transaction without resetting tasks')
    restore.add_argument('--target', required=True)
    restore.add_argument('--transaction', required=True)
    loop = commands.add_parser('loop', help='durable continuous-development queue')
    loop_commands = loop.add_subparsers(dest='loop_command', required=True)
    start = loop_commands.add_parser('start')
    start.add_argument('--plan', required=True)
    start.add_argument('--trust')
    loop_commands.add_parser('status')
    next_action = loop_commands.add_parser('next')
    next_action.add_argument('--worker', default='claude', help='execution label (default: claude)')
    next_action.add_argument('--trust')
    complete = loop_commands.add_parser('complete')
    complete.add_argument('--token', required=True)
    complete.add_argument('--outcome', required=True, choices=['prepared','implemented','reviewed','changes_required','blocked'])
    complete.add_argument('--decision', required=True)
    complete.add_argument('--trust')
    recover = loop_commands.add_parser('recover')
    recover.add_argument('--token', required=True)
    recover.add_argument('--reason', required=True)
    renew = loop_commands.add_parser('renew', help='explicit additive execution budget, not approval or reset')
    target = renew.add_mutually_exclusive_group(required=True)
    target.add_argument('--task')
    target.add_argument('--queue', action='store_true')
    renew.add_argument('--reason', required=True)
    renew.add_argument('--extra-minutes', type=int, default=0)
    renew.add_argument('--extra-attempts', type=int, default=0,
                       help='additional failed runs for a task, scheduling steps for a queue')
    for name in ('retry', 'reconcile'):
        command = loop_commands.add_parser(name)
        command.add_argument('--task', required=True)
        command.add_argument('--reason', required=True)
    return parser


SEED_FOLDERS = ('Docs/Governance', 'Docs/Runbooks', 'Docs/Product', 'Docs/Architecture', 'Docs/ADR', 'Templates')
IMPORT_LINE = '@PIPELINE.md'
IMPORT_BLOCK = '## Web pipeline\n\nThis project follows the web pipeline rules. Start with `python -m web_pipeline status`.\n\n' + IMPORT_LINE + '\n'


def _kit_files(source: Path, folder: str) -> list[Path]:
    return [item for item in sorted((source / folder).rglob('*')) if item.is_file() and '__pycache__' not in item.parts]


def _merged_gitignore(source: Path, target: Path) -> str | None:
    """Existing lines stay untouched and first; only missing pipeline lines are appended."""
    path = target / '.gitignore'
    current = path.read_text(encoding='utf-8-sig') if path.is_file() else ''
    present = {line.strip() for line in current.splitlines()}
    missing = [line for line in (source / 'gitignore.txt').read_text(encoding='utf-8-sig').splitlines()
               if line.strip() and line.strip() not in present]
    if not missing: return None
    head = current if not current or current.endswith('\n') else current + '\n'
    return head + ('\n# web pipeline\n' if current else '') + '\n'.join(missing) + '\n'


def _init(source: Path, target: Path, preview=False, domains=None, ci=False) -> dict:
    """Adopt the engine into a project: engine files must be new, shared project files are merged, the rest is preserved."""
    from .maintenance import MANAGED, location, receipt, RECEIPT
    from .common import atomic_json, atomic_text, safe_path
    source, target = location(source), location(target)
    if source == target or source in target.parents or target in source.parents:
        raise PipelineError("init target must be outside the kit source")
    config = json.loads((source / 'pipeline.config.yaml').read_text(encoding='utf-8-sig'))
    known = list(config['risk']['domain_floor'])
    unknown = [name for name in domains or [] if name not in known]
    if unknown: raise PipelineError('Unknown domain: ' + ', '.join(unknown) + '; choose from ' + ', '.join(known))
    engine = [(item, target / item.relative_to(source)) for folder in MANAGED for item in _kit_files(source, folder)]
    engine += [(source / name, target / name) for name in ('pipeline.config.yaml', 'PIPELINE.md')]
    engine.append((source / 'requirements.txt', target / 'requirements-pipeline.txt'))
    if ci: engine.append((source / 'ci/project-policy.yml', target / '.github/workflows/project-policy.yml'))
    seeds = [(item, target / item.relative_to(source)) for folder in SEED_FOLDERS for item in _kit_files(source, folder)]
    missing = [str(src) for src, _ in engine + seeds if not src.is_file()] + [str(source / 'gitignore.txt')] * (not (source / 'gitignore.txt').is_file())
    if missing: raise PipelineError("kit is incomplete: " + ", ".join(missing))
    conflicts = [str(dst) for _, dst in engine if dst.exists()]
    if safe_path(target, RECEIPT).exists(): conflicts.append(str(target / RECEIPT))
    preserved = sorted(dst.relative_to(target).as_posix() for _, dst in seeds if dst.exists())
    seeds = [(src, dst) for src, dst in seeds if not dst.exists()]
    merged_names = ['CLAUDE.md', '.gitignore']
    destinations = [dst for _, dst in engine + seeds] + [target / name for name in merged_names] + [target / 'Reports/Pipeline/.gitkeep']
    unsafe = sorted({str(dst) for dst in destinations
                     if any(parent.is_symlink() or (hasattr(parent, 'is_junction') and parent.is_junction()) for parent in [dst, *dst.parents])})
    if preview:
        return {'mode':'PREVIEW', 'writes':False, 'target':str(target), 'files':len(engine) + len(seeds),
                'conflicts':conflicts, 'unsafe':unsafe, 'preserved':preserved, 'merged':merged_names,
                'can_adopt':not conflicts and not unsafe,
                'next':'Already adopted projects use upgrade. Otherwise move or rename the conflicting engine paths.' if conflicts else 'Adopt without --preview.'}
    if conflicts: raise PipelineError("init would overwrite existing files: " + ", ".join(conflicts))
    if unsafe: raise PipelineError("init refuses symlink destinations: " + ", ".join(unsafe))
    for src, dst in engine + seeds:
        dst.parent.mkdir(parents=True, exist_ok=True); shutil.copy2(src, dst)
    keep = target / 'Reports/Pipeline/.gitkeep'
    if not keep.exists(): atomic_text(keep, '')
    merged = []
    claude = target / 'CLAUDE.md'
    rules = claude.read_text(encoding='utf-8-sig') if claude.is_file() else ''
    if IMPORT_LINE not in rules.splitlines():
        atomic_text(claude, (rules if not rules or rules.endswith('\n') else rules + '\n') + ('\n' if rules else '# Project instructions\n\n') + IMPORT_BLOCK)
        merged.append('CLAUDE.md')
    ignore = _merged_gitignore(source, target)
    if ignore is not None:
        atomic_text(target / '.gitignore', ignore); merged.append('.gitignore')
    config["project"]["mode"] = "project"
    config["project"]["ready"] = False
    if domains: config['project']['supported_domains'] = list(dict.fromkeys(domains))
    (target / "pipeline.config.yaml").write_text(json.dumps(config, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline='\n')
    atomic_json(target / RECEIPT, receipt(source))  # Only files this adoption installed; project scripts stay project-owned.
    written = sorted(dst.relative_to(target).as_posix() for _, dst in engine + seeds)
    return {"status":"PASS", "target":str(target), "files_copied":len(written), "written":written, "merged":merged,
            "preserved":preserved, "ready":False,
            "next":"Install requirements-pipeline.txt, then configure sources, Git/base refs and real checks before project.ready=true. "
                   "Standard uses local reviews and scoped user receipts without identity/trust; strict keeps signatures."}


def _status(root: Path, task_id=None) -> dict:
    """Read-only orientation for a new session. Never raises for an unadopted or not-ready project."""
    from .common import held_locks, safe_path
    from .maintenance import version
    if not (root / 'pipeline.config.yaml').is_file():
        return {'adopted':False, 'root':str(root), 'next':'No pipeline.config.yaml here: adopt the pipeline first (adopt --preview, then adopt).'}
    result: dict = {'adopted':True, 'root':str(root), 'writes':False}
    try:
        config = load_config(root, kit=True)
    except (PipelineError, ValueError, OSError) as exc:
        return {**result, 'config_error':str(exc), 'next':'Fix pipeline.config.yaml (Docs/Runbooks/CONFIGURATION.md), then run validate.'}
    project = config['project']
    result.update(engine_version=version(root), mode=project['mode'], ready=bool(project.get('ready')),
                  approval_policy=config.get('approval_policy', 'strict'),
                  enabled_checks=[c['id'] for c in config['verification']['commands'] if c['enabled']])
    tasks, broken = [], []
    work = safe_path(root, 'Docs/Work')
    for folder in sorted(work.iterdir()) if work.is_dir() else []:
        if not (folder / 'STATE.md').is_file() or (task_id and folder.name != task_id): continue
        try:
            state = read_state(root, folder.name)
            tasks.append({key: state.get(key) for key in ('task_id', 'title', 'status', 'risk_tier', 'revision', 'iteration')})
        except (PipelineError, ValueError, OSError, KeyError) as exc:
            broken.append({'task_id':folder.name, 'error':str(exc)})
    if task_id and not tasks and not broken:
        raise PipelineError(f'No task {task_id} under Docs/Work; run status without --task to list tasks')
    locks, _ = held_locks(root)
    result.update(tasks=tasks, locks=locks)
    if broken: result['unreadable_tasks'] = broken
    if safe_path(root, 'Docs/Work/AUTOPILOT.json').is_file():
        try:
            from . import autopilot
            queue = autopilot.status(root)
            result['queue'] = {key: queue[key] for key in ('status', 'queue_id', 'paused_reason', 'steps', 'lease')}
        except (PipelineError, ValueError, OSError, KeyError) as exc:
            result['queue'] = {'status':'UNREADABLE', 'error':str(exc)}
    stale = [item['name'] for item in locks if not item['alive']]
    open_tasks = [item for item in tasks if item['status'] != 'DONE']
    if project['mode'] != 'project': hint = 'This is a kit checkout, not an adopted project.'
    elif not result['ready']: hint = 'Project is not ready: configure sources and real checks, set project.ready=true, then run validate.'
    elif stale: hint = 'Stale locks (' + ', '.join(stale) + ') are reclaimed automatically; locks --clear-stale removes them now.'
    elif result.get('queue', {}).get('status') in {'BUSY', 'PAUSED_LIMIT'}: hint = 'A queue is active: loop status, then loop next.'
    elif open_tasks: hint = 'Continue ' + ', '.join(f"{item['task_id']} ({item['status']})" for item in open_tasks[:5]) + '.'
    else: hint = 'No open task: create one with new --task <TaskId> --title ... --domains ...'
    result['next'] = hint
    return result


def dispatch(args: argparse.Namespace) -> dict[str, Any]:
    root = Path(args.root).resolve()
    if args.command == 'clarification-report':
        from .clarifications import report
        return report(root, args.task)
    if args.command == 'loop':
        from . import autopilot
        if args.loop_command == 'start':
            return autopilot.start(root, json.loads(Path(args.plan).read_text(encoding='utf-8-sig')), args.trust)
        if args.loop_command == 'status':
            return autopilot.status(root)
        if args.loop_command == 'next':
            return autopilot.advance(root, args.worker, args.trust)
        if args.loop_command == 'complete':
            return autopilot.complete(root, args.token, args.outcome,
                                      json.loads(Path(args.decision).read_text(encoding='utf-8-sig')), args.trust)
        if args.loop_command == 'recover':
            return autopilot.recover(root, args.token, args.reason)
        if args.loop_command == 'renew':
            return autopilot.renew(root, task_id=args.task, queue_target=args.queue, reason=args.reason,
                                   extra_minutes=args.extra_minutes, extra_attempts=args.extra_attempts)
        if args.loop_command == 'reconcile':
            return autopilot.reconcile(root, args.task, args.reason)
        return autopilot.retry(root, args.task, args.reason)
    if args.command == "init":
        return _init(Path(__file__).resolve().parents[1], Path(args.target), args.preview, _csv(args.domains) or None, args.ci)
    if args.command == 'status': return _status(root, args.task)
    if args.command == 'locks':
        from .common import held_locks
        locks, cleared = held_locks(root, args.clear_stale)
        return {'locks': locks, 'cleared': cleared}
    if args.command in {'inspect','upgrade','restore'}:
        from . import maintenance
        if args.command == 'inspect': return maintenance.diagnose(args.target)
        if args.command == 'restore': return maintenance.restore(args.target, args.transaction)
        return maintenance.upgrade(Path(__file__).resolve().parents[1], args.target, args.baseline, args.apply)
    if args.command == "validate":
        from .state import policy_check
        return policy_check(root, task_id=args.task, kit=args.kit, trust_path=args.trust, base_ref=args.base_ref, gate=args.gate)
    if args.command == "new":
        from .state import create_task
        return create_task(root,args.task,args.title,args.tier,_csv(args.domains),_csv(args.protected),args.migration,args.base_ref)
    if args.command == "transition":
        from .state import transition
        return transition(root,args.task,args.status,trust_path=args.trust)
    if args.command == "prepare":
        from .state import prepare_task
        return prepare_task(root,args.task,args.implementer)
    if args.command == 'review':
        from .local_review import record_review
        return record_review(root, args.task, json.loads(Path(args.decision).read_text(encoding='utf-8-sig')))
    if args.command == 'approval-request':
        from .user_approval import approval_request
        return approval_request(root, args.task, args.phase, args.check_id, trust_path=args.trust)
    if args.command == 'approve':
        from .user_approval import record_approval
        return record_approval(root, args.task, json.loads(Path(args.record).read_text(encoding='utf-8-sig')), trust_path=args.trust)
    if args.command == "attach":
        from .state import attach_record
        return attach_record(root,args.task,args.kind,args.path)
    if args.command == 'archive':
        if args.recover:
            if args.include_members:
                raise PipelineError('--recover cannot be combined with --include-members')
            from .archival import recover_archive
            return recover_archive(root)
        from .state import archive_task
        return archive_task(root,args.task,trust_path=args.trust,include_members=args.include_members)
    if args.command == "revise":
        from .state import revise_task
        return revise_task(root,args.task,args.reason)
    if args.command == 'verification-plan':
        from .scopes import completion_profile, selection
        from .evidence import acceptance_checks, required_checks
        config = load_config(root)
        state = read_state(root, args.task)
        profile = args.profile or completion_profile(root, config, state)
        return selection(root, config, state, profile, trust_path=args.trust) or {
            'profile': profile, 'level': 'legacy',
            'checks': required_checks(config, state, profile, acceptance_checks(root, state))}
    if args.command == "run":
        from .runner import run_profile
        return run_profile(root,args.task,args.profile,trust_path=args.trust,run_id=args.run_id)
    if args.command == "fingerprint":
        config=load_config(root,kit=True); state=read_state(root,args.task)
        return {"task_id":args.task,"fingerprint":source_fingerprint(root,config,state)}
    raise PipelineError("unknown command")


def main(argv: list[str] | None = None) -> int:
    try:
        args=_parser().parse_args(argv)
        result=dispatch(args)
        print(json.dumps(result,indent=2,sort_keys=True,ensure_ascii=False))
        if args.command == 'clarification-report':
            return 0 if result['result'] == 'CLEAR' else 1
        if isinstance(result,dict) and "status" in result and args.command in {"validate","run"}:
            return 0 if result["status"] == "PASS" else 1
        # `loop status` is a read-only query; only actions signal "no work handed out" through the exit code.
        if args.command == 'loop' and args.loop_command != 'status' and result.get('status') in {'WAITING', 'BUSY', 'PAUSED_LIMIT', 'FAIL'}:
            return 1
        return 0
    except (PipelineError, ValueError, OSError) as exc:
        print(json.dumps({"status":"FAIL","error":str(exc)},ensure_ascii=False),file=sys.stderr)
        return 1
