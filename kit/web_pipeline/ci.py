"""Read-only CI context resolution; artifact identifiers are data, never shell code."""
import json
from pathlib import Path
import re
import subprocess

from .common import PipelineError, load_config, output_exclusions, safe_path
from .policy import option_shaped


def resolve_context(root: Path, base_ref: str, evidence_run_id: str = '', force_project: bool = False) -> dict:
    root = Path(root).resolve()
    if not base_ref or option_shaped(base_ref):
        raise PipelineError('CI requires an explicit comparison base ref')
    resolved = subprocess.run(['git', '-C', str(root), 'rev-parse', '--verify', base_ref + '^{commit}'],
                              capture_output=True, text=True, timeout=30)
    base = resolved.stdout.strip()
    if resolved.returncode or not re.fullmatch(r'[a-fA-F0-9]{40}|[a-fA-F0-9]{64}', base):
        raise PipelineError('CI comparison base cannot be resolved to a commit')
    previous = subprocess.run(['git', '-C', str(root), 'show', base + ':pipeline.config.yaml'],
                              capture_output=True, text=True, encoding='utf-8', timeout=30)
    prior = json.loads(previous.stdout) if previous.returncode == 0 else {}
    config = load_config(root, kit=True)
    project = (force_project or config['project']['mode'] == 'project'
               or prior.get('project', {}).get('mode') == 'project')
    if project and config['project']['mode'] != 'project':
        raise PipelineError('An adopted project cannot bypass its CI gate by switching to kit mode')
    if project and not evidence_run_id:
        manifest = safe_path(root, 'Docs/Work/CI_EVIDENCE.json', True)
        data = json.loads(manifest.read_text(encoding='utf-8-sig'))
        if not isinstance(data, dict) or set(data) != {'workflow_run_id'}:
            raise PipelineError('CI_EVIDENCE.json must contain only workflow_run_id')
        evidence_run_id = data['workflow_run_id']
    if project and (not isinstance(evidence_run_id, str)
                    or not re.fullmatch(r'[1-9][0-9]{0,19}', evidence_run_id)):
        raise PipelineError('CI evidence workflow_run_id must be a positive numeric string')
    report, _ = output_exclusions(root, config)
    return {'project': project, 'base_ref': base, 'evidence_run_id': evidence_run_id if project else '',
            'report_root': report}
