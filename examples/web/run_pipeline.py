"""Execute an isolated real web task; retain the project and original evidence."""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import uuid

REPO = Path(__file__).resolve().parents[2]
KIT = REPO / 'kit'
sys.path.insert(0, str(KIT))
from web_pipeline.common import atomic_json, atomic_text, hash_file, utc_now


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--node-tools', required=True, help='directory containing installed @playwright/test and typescript')
    parser.add_argument('--browsers', help='optional existing Playwright browser cache')
    args = parser.parse_args()
    tools = Path(args.node_tools).resolve()
    playwright = tools / '@playwright/test/cli.js'
    if not playwright.is_file() or not (tools / 'typescript').is_dir():
        parser.error('Install the scoped Node dependencies before running; no implicit installer')
    node = shutil.which('node')
    if not node: parser.error('Node 22.15+ is required')
    report = REPO / 'Reports/Pipeline' / ('web-example-' + uuid.uuid4().hex[:12])
    report.mkdir(parents=True, exist_ok=False)
    env = {**os.environ, 'NODE_PATH': str(tools), 'WEB_PIPELINE_DEMO': '1'}
    if args.browsers: env['PLAYWRIGHT_BROWSERS_PATH'] = str(Path(args.browsers).resolve())
    started = utc_now()
    with tempfile.TemporaryDirectory(prefix='web-pipeline-real-demo-') as temporary:
        root = Path(temporary) / 'project'
        log_path = report / 'execution.log'
        with log_path.open('w', encoding='utf-8') as log:
            def run(command, cwd=root, expected=0):
                log.write(json.dumps(command) + '\n'); log.flush()
                result = subprocess.run(command, cwd=cwd, env=env, stdout=log, stderr=subprocess.STDOUT, timeout=240)
                if result.returncode != expected: raise RuntimeError(f'Unexpected exit {result.returncode}: {command}')
            try:
                run([sys.executable, '-m', 'web_pipeline', 'init', '--target', str(root)], KIT)
                example = REPO / 'examples/web'
                for relative in ('src', 'tests'):
                    destination = root / ('web-tests' if relative == 'tests' else relative)
                    shutil.copytree(example / relative, destination)
                for relative in ('playwright.config.cjs', 'reporter.cjs', 'syntax.cjs'):
                    shutil.copyfile(example / relative, root / relative)
                config_text = (root / 'playwright.config.cjs').read_text(encoding='utf-8')
                atomic_text(root / 'playwright.config.cjs', config_text.replace("testDir: './tests'", "testDir: './web-tests'"))
                config = json.loads((root / 'pipeline.config.yaml').read_text(encoding='utf-8'))
                config['project'].update(name='local-web-reference', ready=True, supported_domains=['frontend','backend','api'])
                config['verification']['policy_checks'] = []
                profiles = ['Policy','Baseline','Fast','Full','Release']
                # Initial stack-specific commands, not dummy substitutes for absent tooling.
                commands = [('js-syntax',[node,'syntax.cjs'],[]),
                    ('web-tests',[node,str(playwright),'test','--config','playwright.config.cjs'],['artifacts/web-tests.json']),
                    ('boundary-imports',[node,'Scripts/boundary-graph.cjs'],['artifacts/boundary-graph.json'])]
                config['verification']['commands'] += [dict(id=name,enabled=True,profiles=profiles,argv=argv,cwd='.',timeout_seconds=120,artifacts=artifacts,environment='test') for name,argv,artifacts in commands]
                next(c for c in config['verification']['commands'] if c['id']=='web-tests')['test_report'] = {
                    'path':'artifacts/web-tests.json','min_tests':6,'max_skipped':0,
                    'required_groups':['provider','consumer','compatibility','security','database','browser']}
                for domain in config['project']['supported_domains']:
                    for profile in profiles[1:]: config['verification']['requirements'][domain][profile] = ['js-syntax','web-tests']
                config['boundaries'] = {'source_patterns':['src/*'], 'dependency_check':'boundary-imports', 'server_only_packages':[],
                    'components':[{'id':'web','runtime':'browser','paths':['src/client/*'],'depends_on':['shared']},
                        {'id':'api','runtime':'server','paths':['src/server/*'],'depends_on':['shared']},
                        {'id':'shared','runtime':'shared','paths':['src/shared/*'],'depends_on':[]}],
                    'contracts':[{'id':'notes','paths':['src/shared/contract.json'],'provider':'api','consumers':['web'],
                        'checks':{role:'web-tests' for role in ('provider','consumer','compatibility','integration')}}]}
                atomic_json(root / 'pipeline.config.yaml', config)
                for name, relative in config['sources'].items():
                    atomic_text(root / relative, f'# Local reference: {name}\n\nLoopback-only notes demo; fictitious fixed reader/writer roles, SQLite test data, no production use. UI, API and persistence are verified with real requests and browser evidence.\n')
                for command in (['git','init','-q'], ['git','config','user.name','Local test fixture'],
                    ['git','config','user.email','fixture@example.invalid'], ['git','config','core.autocrlf','false'],
                    ['git','add','.'], ['git','commit','-qm','Preexisting local demonstration baseline']): run(command)
                cli = [sys.executable,'-B','-m','web_pipeline','--root',str(root)]
                task = 'WEB-DEMO'
                run(cli + ['new','--task',task,'--title','Clarify the verified demo heading','--tier','T2','--domains','frontend,backend,api','--base-ref','HEAD'])
                task_dir = root / 'Docs/Work' / task
                for name, content in {
                    'BRIEF.md':'Update the notes heading while retaining existing API and role behavior.',
                    'DOR.md':'The local preexisting demo, source documents, contract and actual checks are configured.',
                    'PLAN.md':'Capture Baseline; exercise a detectable import regression; repair the heading; pause/resume; verify real browser/API/DB checks; record self-review.'}.items(): atomic_text(task_dir / name, '# Demo task\n\n' + content + '\n')
                atomic_json(task_dir / 'ACCEPTANCE.json', {'criteria':[{'id':'AC-1','description':'Existing real browser/API/data flows and denied requests remain valid','checks':['web-tests','js-syntax','boundary-imports']}]})
                planning = json.loads((task_dir / 'CLARIFICATIONS.json').read_text(encoding='utf-8'))
                findings = ['Change only the notes heading.', 'Retain the existing browser create/list flow.',
                            'Retain existing invalid and denied request behavior.',
                            'Retain the current API contract and disposable SQLite persistence.',
                            'Loopback demo only; no production execution or changed access control.',
                            'AC-1 requires the real browser, API, data and boundary checks.']
                for entry, finding in zip(planning['analysis'], findings):
                    entry.update(finding=finding, sources=[{'kind':'document', 'reference':f'Docs/Work/{task}/BRIEF.md',
                        'excerpt':'Update the notes heading while retaining existing API and role behavior.'}])
                atomic_json(task_dir / 'CLARIFICATIONS.json', planning)
                run(cli + ['prepare','--task',task])
                run(cli + ['run','--task',task,'--profile','Baseline','--run-id','demo-baseline'])
                for state in ('READY','IN_PROGRESS'): run(cli + ['transition','--task',task,'--status',state])
                app = root / 'src/client/app.mjs'
                original = app.read_text(encoding='utf-8')
                atomic_text(app, original + "\nimport '../server/server.cjs';\n")
                run(cli + ['run','--task',task,'--profile','Fast','--run-id','demo-regression'], expected=1)
                regression = json.loads((root / 'Reports/Pipeline/demo-regression/summary.json').read_text())
                if not any(c['id']=='boundary-imports' and c['status']=='FAIL' for c in regression['checks']):
                    raise RuntimeError('The intended boundary regression was not detected')
                atomic_text(app, original.replace('<h1>Pipeline Notes</h1>', '<h1>Pipeline Notes · verified</h1>'))
                for state in ('BLOCKED','IN_PROGRESS','VERIFYING'): run(cli + ['transition','--task',task,'--status',state])
                run(cli + ['run','--task',task,'--profile','Full','--run-id','demo-full'])
                run(cli + ['transition','--task',task,'--status','REVIEW'])
                atomic_json(task_dir / 'decision.json', {'choice':'Accept the scoped heading change',
                    'rationale':'Actual browser/API/SQLite checks pass after repairing the retained boundary failure.',
                    'alternatives':['Separate frontend/backend deployments are unnecessary for this local reference'],
                    'risks':['Self-review of an unprotected demo task, not independent review or production approval']})
                run(cli + ['review','--task',task,'--decision',f'Docs/Work/{task}/decision.json'])
                run(cli + ['transition','--task',task,'--status','DONE'])
                run(cli + ['validate','--gate','merge','--base-ref','HEAD'])
                status, error = 'PASS', None
            except Exception as exc:
                status, error = 'FAIL', str(exc)
                log.write(error + '\n')
        if root.exists(): shutil.copytree(root, report / 'project', ignore=shutil.ignore_patterns('.git','__pycache__','.python-cache','node_modules'))
    summary = {'status':status,'error':error,'started_utc':started,'completed_utc':utc_now(),
        'log':{'path':'execution.log','sha256':hash_file(log_path)},
        'state_path':'project/Docs/Work/WEB-DEMO/STATE.md', 'scope':'isolated example, not production or protected approval'}
    atomic_json(report / 'example-validation.json', summary)
    print(json.dumps({'report':str(report), **summary}, indent=2))
    return 0 if status == 'PASS' else 1


if __name__ == '__main__': raise SystemExit(main())
