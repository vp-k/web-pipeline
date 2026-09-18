"""Reproductions of friction observed in adopted projects."""
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

from web_pipeline import cli, maintenance as m, process_tree
from web_pipeline.common import PipelineError, atomic_json, atomic_text, code_snapshot, hash_file, lock

ROOT = Path(__file__).resolve().parents[1] / 'kit'


def dead_pid():
    done = subprocess.Popen([sys.executable, '-c', 'pass'])
    done.wait()
    return done.pid


class Temp(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup)
        self.work = Path(temp.name).resolve()


class CommandResolutionTests(Temp):
    @unittest.skipUnless(os.name == 'nt', 'PATHEXT resolution is a Windows concern')
    def test_bare_command_name_resolves_cmd_shim_like_npm(self):
        tools = self.work / 'tools'; tools.mkdir()
        (tools / 'faketool.cmd').write_text('@echo off\r\necho shim-ran\r\nexit /b 0\r\n', encoding='ascii')
        env = dict(os.environ); env['PATH'] = str(tools) + os.pathsep + env['PATH']
        log_path = self.work / 'out.log'
        with log_path.open('wb') as log:
            code, reason = process_tree.execute(['faketool'], self.work, env, log, 60, self.work / 'status.json')
        self.assertEqual((0, None), (code, reason))
        self.assertIn('shim-ran', log_path.read_text(encoding='utf-8', errors='replace'))

    @unittest.skipIf(os.name == 'nt', 'POSIX PATH lookup of an executable script')
    def test_bare_command_name_resolves_posix_script_on_path(self):
        tools = self.work / 'tools'; tools.mkdir()
        script = tools / 'faketool'
        script.write_text('#!/bin/sh\necho shim-ran\n', encoding='ascii'); script.chmod(0o755)
        env = dict(os.environ); env['PATH'] = str(tools) + os.pathsep + env['PATH']
        log_path = self.work / 'out.log'
        with log_path.open('wb') as log:
            code, reason = process_tree.execute(['faketool'], self.work, env, log, 60, self.work / 'status.json')
        self.assertEqual((0, None), (code, reason))
        self.assertIn('shim-ran', log_path.read_text(encoding='utf-8', errors='replace'))

    def test_resolve_searches_the_given_env_path_not_the_process_path(self):
        tools = self.work / 'tools'; tools.mkdir()
        name = 'faketool.cmd' if os.name == 'nt' else 'faketool'
        script = tools / name
        script.write_text('@echo off\r\n' if os.name == 'nt' else '#!/bin/sh\n', encoding='ascii'); script.chmod(0o755)
        found = process_tree.resolve(['faketool', 'x'], {'PATH': str(tools)})
        self.assertEqual(['x'], found[1:])
        self.assertTrue(os.path.samefile(script, found[0]), found[0])
        self.assertEqual(['faketool', 'x'], process_tree.resolve(['faketool', 'x'], {'PATH': str(self.work / 'empty')}))

    def test_unknown_command_still_reports_launch_error(self):
        with (self.work / 'out.log').open('wb') as log, self.assertRaises(OSError):
            process_tree.execute(['definitely-not-a-real-command-7f3a'], self.work, dict(os.environ), log, 60,
                                 self.work / 'status.json')


class StaleLockTests(Temp):
    def held(self, name, pid):
        atomic_text(self.work / f'.pipeline-locks/{name}.lock', json.dumps({'pid': pid, 'started_utc': '2026-01-01T00:00:00Z'}))

    def test_lock_of_dead_process_is_reclaimed(self):
        self.held('task-A', dead_pid())
        with lock(self.work, 'task-A'):
            owner = json.loads((self.work / '.pipeline-locks/task-A.lock').read_text(encoding='utf-8'))
            self.assertEqual(os.getpid(), owner['pid'])
        self.assertFalse((self.work / '.pipeline-locks/task-A.lock').exists())

    def test_lock_of_live_process_and_unreadable_lock_still_block(self):
        self.held('task-A', os.getpid())
        with self.assertRaisesRegex(PipelineError, 'holds lock task-A'):
            with lock(self.work, 'task-A'): pass
        atomic_text(self.work / '.pipeline-locks/task-B.lock', 'not json')
        with self.assertRaisesRegex(PipelineError, 'holds lock task-B'):
            with lock(self.work, 'task-B'): pass
        self.assertTrue((self.work / '.pipeline-locks/task-B.lock').exists())

    def test_locks_command_reports_liveness_and_clears_only_stale(self):
        self.held('task-A', dead_pid()); self.held('task-B', os.getpid())
        listed = cli.dispatch(cli._parser().parse_args(['--root', str(self.work), 'locks']))
        self.assertEqual({'task-A': False, 'task-B': True}, {item['name']: item['alive'] for item in listed['locks']})
        self.assertTrue((self.work / '.pipeline-locks/task-A.lock').exists())
        cleared = cli.dispatch(cli._parser().parse_args(['--root', str(self.work), 'locks', '--clear-stale']))
        self.assertEqual(['task-A'], cleared['cleared'])
        self.assertFalse((self.work / '.pipeline-locks/task-A.lock').exists())
        self.assertTrue((self.work / '.pipeline-locks/task-B.lock').exists())


class EncodingTests(unittest.TestCase):
    def test_engine_never_reads_text_without_bom_tolerant_encoding(self):
        # Windows PowerShell 5.1 writes UTF-8 with a BOM; every reader must tolerate it.
        offenders = []
        for path in sorted((ROOT / 'web_pipeline').glob('*.py')):
            for number, line in enumerate(path.read_text(encoding='utf-8').splitlines(), 1):
                for call in re.findall(r'read_text\(([^)]*)\)', line):
                    if 'utf-8-sig' not in call:
                        offenders.append(f'{path.name}:{number}')
        self.assertEqual([], offenders)


class Managed(Temp):
    def setUp(self):
        super().setUp()
        self.old, self.new, self.target = [self.work / name for name in ('old', 'new', 'project')]
        for root in (self.old, self.new):
            for folder in m.MANAGED:
                shutil.copytree(ROOT / folder, root / folder, ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
            shutil.copy2(ROOT / 'pipeline.config.yaml', root / 'pipeline.config.yaml')
        atomic_text(self.old / 'web_pipeline/__init__.py', '__version__ = "2.6.0"\n')
        atomic_text(self.new / 'web_pipeline/__init__.py', '__version__ = "2.7.0"\n')
        atomic_text(self.new / 'Scripts/new-check.py', 'print("new")\n')
        shutil.copytree(self.old, self.target)
        config = json.loads((self.target / 'pipeline.config.yaml').read_text(encoding='utf-8-sig'))
        config['project']['mode'] = 'project'
        atomic_json(self.target / 'pipeline.config.yaml', config)
        atomic_json(self.target / m.RECEIPT, m.receipt(self.target))


class ProjectOwnedFilesTests(Managed):
    def test_project_added_script_is_preserved_not_a_conflict(self):
        atomic_text(self.target / 'Scripts/project-check.ps1', 'Write-Output "mine"\n')
        plan = m.upgrade(self.new, self.target)
        self.assertEqual(['Scripts/project-check.ps1'], plan['project_owned'])
        applied = m.upgrade(self.new, self.target, apply=True)
        self.assertEqual('APPLIED', applied['mode'])
        self.assertEqual('Write-Output "mine"\n', (self.target / 'Scripts/project-check.ps1').read_text(encoding='utf-8'))
        self.assertEqual('__version__ = "2.7.0"\n', (self.target / 'web_pipeline/__init__.py').read_text(encoding='utf-8'))
        m.restore(self.target, applied['transaction'])
        self.assertEqual('__version__ = "2.6.0"\n', (self.target / 'web_pipeline/__init__.py').read_text(encoding='utf-8'))
        self.assertTrue((self.target / 'Scripts/project-check.ps1').is_file())

    def test_project_file_colliding_with_a_new_engine_file_blocks(self):
        atomic_text(self.target / 'Scripts/new-check.py', 'print("mine")\n')
        with self.assertRaisesRegex(PipelineError, 'collide'):
            m.upgrade(self.new, self.target)

    def test_project_file_inside_engine_package_still_blocks(self):
        atomic_text(self.target / 'web_pipeline/extra.py', 'x = 1\n')
        with self.assertRaisesRegex(PipelineError, 'Locally modified'):
            m.upgrade(self.new, self.target)

    def test_receipt_with_bom_is_readable(self):
        path = self.target / m.RECEIPT
        path.write_bytes(b'\xef\xbb\xbf' + path.read_bytes())
        self.assertFalse(m.upgrade(self.new, self.target)['writes'])


class AdoptionTests(Temp):
    def test_existing_project_files_are_merged_or_preserved_never_overwritten(self):
        target = self.work / 'site'
        atomic_text(target / 'README.md', 'my readme\n')
        atomic_text(target / 'CLAUDE.md', '# My rules\n')
        atomic_text(target / '.gitignore', 'node_modules/\n.env\n')
        atomic_text(target / 'requirements.txt', 'django==5.0\n')
        atomic_text(target / 'tests/test_mine.py', 'x = 1\n')
        preview = cli._init(ROOT, target, preview=True)
        self.assertTrue(preview['can_adopt'], preview)
        cli._init(ROOT, target)
        self.assertEqual('my readme\n', (target / 'README.md').read_text(encoding='utf-8'))
        self.assertEqual('django==5.0\n', (target / 'requirements.txt').read_text(encoding='utf-8'))
        self.assertTrue((target / 'requirements-pipeline.txt').is_file())
        claude = (target / 'CLAUDE.md').read_text(encoding='utf-8')
        self.assertTrue(claude.startswith('# My rules\n')); self.assertIn('@PIPELINE.md', claude)
        self.assertTrue((target / 'PIPELINE.md').is_file())
        ignore = (target / '.gitignore').read_text(encoding='utf-8').splitlines()
        self.assertEqual(['node_modules/', '.env'], ignore[:2])
        self.assertIn('.pipeline-locks/', ignore); self.assertEqual(1, ignore.count('node_modules/'))
        self.assertEqual(['test_mine.py'], [p.name for p in (target / 'tests').iterdir()])
        for absent in ('examples', '.github', 'AGENTS.md'):
            self.assertFalse((target / absent).exists(), absent)

    def test_adoption_into_empty_target_creates_claude_import_and_receipt(self):
        target = self.work / 'fresh'
        result = cli._init(ROOT, target)
        self.assertEqual('PASS', result['status'])
        self.assertIn('@PIPELINE.md', (target / 'CLAUDE.md').read_text(encoding='utf-8'))
        self.assertTrue((target / m.RECEIPT).is_file())
        self.assertTrue((target / 'Docs/Governance/00_OPERATING_MODEL.md').is_file())

    def test_engine_folder_conflict_still_blocks_without_writes(self):
        target = self.work / 'site'
        atomic_text(target / 'web_pipeline/cli.py', 'mine\n')
        self.assertFalse(cli._init(ROOT, target, preview=True)['can_adopt'])
        with self.assertRaisesRegex(PipelineError, 'overwrite'):
            cli._init(ROOT, target)
        self.assertFalse((target / 'pipeline.config.yaml').exists())

    def test_domains_trim_supported_domains_and_ci_is_opt_in(self):
        target = self.work / 'static'
        cli._init(ROOT, target, domains=['frontend'], ci=True)
        config = json.loads((target / 'pipeline.config.yaml').read_text(encoding='utf-8'))
        self.assertEqual(['frontend'], config['project']['supported_domains'])
        workflow = (target / '.github/workflows/project-policy.yml').read_text(encoding='utf-8')
        # Adoption ships requirements-pipeline.txt; the workflow must install that, not the project's own file.
        self.assertIn('pip install -r requirements-pipeline.txt', workflow)
        self.assertLess(workflow.index('requirements-pipeline.txt'), workflow.index('-r requirements.txt'))
        with self.assertRaisesRegex(PipelineError, 'Unknown domain'):
            cli._init(ROOT, self.work / 'bad', domains=['frontend', 'blockchain'])


class GitAwareDigestTests(Temp):
    def git(self, *args):
        subprocess.run(['git', '-C', str(self.work), *args], check=True, capture_output=True)

    def config(self, respect):
        config = json.loads((ROOT / 'pipeline.config.yaml').read_text(encoding='utf-8-sig'))
        config['project']['generated_paths'] = []
        if respect is None:
            config['project'].pop('respect_gitignore', None)
        else:
            config['project']['respect_gitignore'] = respect
        return config

    def test_a_config_without_the_key_respects_gitignore_by_default(self):
        atomic_text(self.work / 'src/index.ts', 'export {}\n')
        atomic_text(self.work / '.gitignore', '.turbo/\n')
        self.git('init', '-q'); self.git('config', 'user.email', 't@example.invalid'); self.git('config', 'user.name', 'T')
        self.git('add', '.'); self.git('commit', '-qm', 'base')
        before = code_snapshot(self.work, self.config(None))['tree_digest']
        atomic_text(self.work / '.turbo/cache.bin', 'x')
        self.assertEqual(before, code_snapshot(self.work, self.config(None))['tree_digest'])

    def test_ignored_nested_build_output_does_not_change_the_digest(self):
        atomic_text(self.work / 'apps/web/src/index.ts', 'export {}\n')
        atomic_text(self.work / '.gitignore', '.turbo/\n*.tsbuildinfo\n')
        self.git('init', '-q'); self.git('config', 'user.email', 't@example.invalid'); self.git('config', 'user.name', 'T')
        self.git('add', '.'); self.git('commit', '-qm', 'base')
        for respect in (True, False):
            with self.subTest(respect_gitignore=respect):
                before = code_snapshot(self.work, self.config(respect))['tree_digest']
                atomic_text(self.work / 'apps/web/.turbo/cache.bin', str(respect))
                atomic_text(self.work / 'apps/web/tsconfig.tsbuildinfo', str(respect))
                after = code_snapshot(self.work, self.config(respect))['tree_digest']
                (self.assertEqual if respect else self.assertNotEqual)(before, after)
        before = code_snapshot(self.work, self.config(True))['tree_digest']
        atomic_text(self.work / 'apps/web/src/new.ts', 'export const untracked = 1\n')
        self.assertNotEqual(before, code_snapshot(self.work, self.config(True))['tree_digest'])

    def test_kit_config_enables_it_and_schema_accepts_the_key(self):
        from web_pipeline.common import validate_schema
        config = json.loads((ROOT / 'pipeline.config.yaml').read_text(encoding='utf-8-sig'))
        self.assertIs(True, config['project']['respect_gitignore'])
        validate_schema(ROOT, 'config', config)


class StatusTests(Temp):
    def test_status_on_unadopted_directory_is_a_hint_not_a_crash(self):
        result = cli.dispatch(cli._parser().parse_args(['--root', str(self.work), 'status']))
        self.assertFalse(result['adopted']); self.assertIn('adopt', result['next'])

    def test_status_lists_tasks_locks_and_readiness_without_writes(self):
        target = self.work / 'p'
        cli._init(ROOT, target)
        atomic_text(target / '.pipeline-locks/task-Z.lock', json.dumps({'pid': dead_pid(), 'started_utc': '2026-01-01T00:00:00Z'}))
        before = {p.relative_to(target).as_posix(): hash_file(p) for p in target.rglob('*') if p.is_file()}
        result = cli.dispatch(cli._parser().parse_args(['--root', str(target), 'status']))
        self.assertTrue(result['adopted']); self.assertFalse(result['ready'])
        self.assertEqual([], result['tasks'])
        self.assertEqual([{'name': 'task-Z', 'alive': False}], [{k: item[k] for k in ('name', 'alive')} for item in result['locks']])
        self.assertIn('ready', result['next'])
        self.assertEqual(before, {p.relative_to(target).as_posix(): hash_file(p) for p in target.rglob('*') if p.is_file()})


class ValidateWithoutTasksTests(Temp):
    """A ready project with no tasks yet must still be able to validate its configuration."""
    def ready_project(self):
        import copy
        from web_pipeline.common import load_config
        root = self.work / 'p'; root.mkdir()
        config = copy.deepcopy(load_config(ROOT, kit=True))
        config['project'].update(mode='project', ready=True, supported_domains=['backend'])
        atomic_text(root / 'check.py', 'print("ok")\n')
        for command in config['verification']['commands']:
            command.update(enabled=True, argv=[sys.executable, 'check.py'], artifacts=[])
        for path in config['sources'].values():
            atomic_text(root / path, 'Fixture source.\n')
        atomic_json(root / 'pipeline.config.yaml', config)
        for args in (('init', '-q'), ('config', 'user.email', 't@example.invalid'), ('config', 'user.name', 'T'),
                     ('add', '.'), ('commit', '-qm', 'base')):
            subprocess.run(['git', '-C', str(root), *args], check=True, capture_output=True)
        return root

    def test_progress_gate_passes_with_a_warning_when_no_task_exists(self):
        from web_pipeline.state import policy_check
        root = self.ready_project()
        result = policy_check(root)
        self.assertEqual('PASS', result['status'], result)
        self.assertTrue(any('no tasks' in w for w in result['warnings']), result)

    def test_merge_gate_still_refuses_an_empty_task_set(self):
        from web_pipeline.state import policy_check
        root = self.ready_project()
        result = policy_check(root, gate='merge')
        self.assertEqual('FAIL', result['status'], result)
        self.assertTrue(any('no tasks' in e for e in result['errors']), result)


class LockfileRuleTests(unittest.TestCase):
    def test_default_lock_rule_matches_lockfiles_not_words_containing_lock(self):
        import fnmatch
        config = json.loads((ROOT / 'pipeline.config.yaml').read_text(encoding='utf-8-sig'))
        patterns = [rule['pattern'] for rule in config['risk']['path_rules'] if 'major_framework_sdk' in rule['protected_changes']
                    or 'lock' in rule['pattern'].lower()]
        def hit(path): return any(fnmatch.fnmatchcase(path, pattern) for pattern in patterns)
        for path in ('package-lock.json', 'web/pnpm-lock.yaml', 'yarn.lock', 'api/poetry.lock', 'Cargo.lock', 'go.sum', 'uv.lock'):
            self.assertTrue(hit(path), path)
        for path in ('src/components/BlockList.tsx', 'src/hooks/useClock.ts', 'src/unlock/page.tsx'):
            self.assertFalse(hit(path), path)


class GitRefTests(Temp):
    """A base_ref is a revision, never a git option."""
    def git(self, *args):
        subprocess.run(['git', '-C', str(self.work), *args], check=True, capture_output=True)

    def test_option_shaped_base_ref_is_rejected_before_git_sees_it(self):
        from web_pipeline.policy import _changed_paths
        from web_pipeline.state import create_task
        atomic_text(self.work / 'a.txt', 'a')
        self.git('init', '-q'); self.git('config', 'user.email', 't@example.invalid'); self.git('config', 'user.name', 'T')
        self.git('add', '.'); self.git('commit', '-qm', 'base')
        for bad in ('--output=pwned.txt', '-x', ' --stat'):
            with self.subTest(base_ref=bad):
                paths, errors = _changed_paths(self.work, bad)
                self.assertEqual([], paths); self.assertEqual(1, len(errors)); self.assertIn('base_ref', errors[0])
                self.assertFalse((self.work / 'pwned.txt').exists())
        shutil.copytree(ROOT, self.work / 'kit', ignore=shutil.ignore_patterns('__pycache__'))
        with self.assertRaisesRegex(PipelineError, 'base_ref'):
            create_task(self.work / 'kit', 'T-1', 'x', 'T1', ['backend'], base_ref='--output=pwned.txt')
        self.assertEqual([], _changed_paths(self.work, 'HEAD')[1])


if __name__ == '__main__':
    unittest.main()
