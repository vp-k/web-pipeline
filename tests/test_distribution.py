"""The plugin as shipped: manifests, bootstrap, and a real adoption through the bootstrap."""
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

REPO = Path(__file__).resolve().parents[1]
BOOTSTRAP = REPO / 'scripts/pipeline.py'


def run(*arguments, cwd=REPO):
    return subprocess.run([sys.executable, '-B', *map(str, arguments)], cwd=cwd, capture_output=True, text=True, timeout=120)


class ReleaseFilesTests(unittest.TestCase):
    def test_manifest_and_plugin_version_are_current(self):
        result = run(REPO / 'tools/release.py', '--check')
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)

    def test_plugin_manifest_points_at_existing_components(self):
        plugin = json.loads((REPO / '.claude-plugin/plugin.json').read_text(encoding='utf-8'))
        self.assertRegex(plugin['version'], r'^2\.\d+\.\d+$')  # The engine refuses upgrades to another major.
        for entry in plugin['commands'] + plugin['skills']:
            self.assertTrue((REPO / entry).is_dir(), entry)
        self.assertTrue((REPO / 'skills/web-pipeline/SKILL.md').is_file())

    def test_every_component_has_frontmatter_with_a_description(self):
        files = [*(REPO / 'commands').glob('*.md'), *(REPO / 'agents').glob('*.md'), REPO / 'skills/web-pipeline/SKILL.md']
        self.assertGreaterEqual(len(files), 7)
        for path in files:
            text = path.read_text(encoding='utf-8')
            match = re.match(r'---\n(.*?)\n---\n', text, re.S)
            self.assertIsNotNone(match, path.name)
            self.assertRegex(match[1], r'(?m)^description: \S', path.name)

    def test_skill_routes_only_to_references_that_exist(self):
        skill = (REPO / 'skills/web-pipeline/SKILL.md').read_text(encoding='utf-8')
        names = set(re.findall(r'references/([a-z-]+\.md)', skill))
        self.assertTrue(names)
        for name in names:
            self.assertTrue((REPO / 'skills/web-pipeline/references' / name).is_file(), name)

    def test_shipped_text_has_no_leftovers_from_the_codex_edition(self):
        offenders = []
        for top in ('commands', 'agents', 'skills', 'kit'):
            for path in (REPO / top).rglob('*'):
                if path.is_file() and path.suffix in {'.md', '.py', '.ps1', '.yaml', '.yml', '.json', '.txt'} and '__pycache__' not in path.parts:
                    if re.search(r'(?i)codex|\$web-development-pipeline', path.read_text(encoding='utf-8-sig')):
                        offenders.append(path.relative_to(REPO).as_posix())
        self.assertEqual([], offenders)


class BootstrapTests(unittest.TestCase):
    def setUp(self):
        self.work = Path(tempfile.mkdtemp(prefix='plugin-dist-'))
        self.addCleanup(shutil.rmtree, self.work, True)

    def test_doctor_verifies_the_bundle(self):
        result = run(BOOTSTRAP, 'doctor')
        report = json.loads(result.stdout)
        self.assertEqual('PASS', report['status'], result.stdout + result.stderr)
        self.assertEqual(json.loads((REPO / 'kit-manifest.json').read_text(encoding='utf-8'))['engine_version'], report['engine_version'])

    def test_adopt_then_project_local_engine_answers_status(self):
        target = self.work / 'site'
        target.mkdir()
        (target / 'CLAUDE.md').write_text('# Mine\n', encoding='utf-8')
        preview = run(BOOTSTRAP, 'adopt', '--target', target, '--preview')
        self.assertTrue(json.loads(preview.stdout)['can_adopt'], preview.stdout + preview.stderr)
        self.assertFalse((target / 'web_pipeline').exists())
        adopted = run(BOOTSTRAP, 'adopt', '--target', target, '--domains', 'frontend,backend,api')
        self.assertEqual(0, adopted.returncode, adopted.stdout + adopted.stderr)
        status = run('-m', 'web_pipeline', 'status', cwd=target)  # The project's own copy, not the plugin's.
        report = json.loads(status.stdout)
        self.assertTrue(report['adopted']); self.assertFalse(report['ready'])
        self.assertEqual('project', report['mode'])
        upgrade = run(BOOTSTRAP, 'upgrade', '--target', target)
        self.assertEqual([], json.loads(upgrade.stdout)['changed'], upgrade.stdout + upgrade.stderr)

    def test_target_inside_the_plugin_is_refused(self):
        result = run(BOOTSTRAP, 'adopt', '--target', REPO / 'kit' / 'nested', '--preview')
        self.assertEqual(1, result.returncode)
        self.assertIn('outside the installed plugin', result.stderr)


if __name__ == '__main__':
    unittest.main()
