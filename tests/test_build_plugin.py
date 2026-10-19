"""Archive layouts and installation checks use isolated source/user folders."""
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('package_builder', ROOT / 'scripts/build_plugin.py')
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)
spec = importlib.util.spec_from_file_location('package_installer', ROOT / 'install.py')
installer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(installer)


class PackagingTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.repo = Path(self.temporary.name) / 'source'
        self.repo.mkdir()
        for relative in ('plugin.json', '.codex-plugin/plugin.json', '.claude-plugin/plugin.json',
                         '.claude-plugin/marketplace.json', 'mcp.json', '.mcp.json', 'LICENSE', 'pyproject.toml'):
            self.write(relative, (ROOT / relative).read_text(encoding='utf-8'))
        for relative in installer.REQUIRED_FILES:
            content = '---\nname: academyinfo-flow\ndescription: synthetic package fixture\n---\n' if relative == 'SKILL.md' else '# synthetic package fixture\n'
            self.write('skills/academyinfo-flow/' + relative, content)
        self.write('skills/academyinfo-flow/references/guide.json', '{"synthetic":true}\n')
        self.write('skills/academyinfo-flow/agents/openai.yaml', 'interface:\n  display_name: "대학알리미FLOW"\n')
        self.write('skills/academyinfo-flow/__pycache__/cache.pyc', 'cache')
        self.write('skills/academyinfo-flow/.venv/private.txt', 'excluded environment')

    def write(self, relative, text):
        path = self.repo / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding='utf-8')

    def build(self):
        with patch.object(builder, 'ROOT', self.repo):
            return builder.build_all()

    def test_three_archives_have_distinct_layouts_and_identical_core_bytes(self):
        paths = self.build()
        self.assertEqual(len(set(paths.values())), 3)
        with zipfile.ZipFile(paths['plugin']) as plugin, zipfile.ZipFile(paths['codex_skill']) as codex, zipfile.ZipFile(paths['claude_web_skill']) as claude:
            self.assertIn('plugin.json', plugin.namelist())
            self.assertIn('mcp.json', plugin.namelist())
            self.assertIn('.mcp.json', plugin.namelist())
            self.assertIn('pyproject.toml', plugin.namelist())
            self.assertIn('skills/academyinfo-flow/SKILL.md', plugin.namelist())
            self.assertIn('academyinfo-flow/agents/openai.yaml', codex.namelist())
            self.assertNotIn('academyinfo-flow/agents/openai.yaml', claude.namelist())
            for archive in (codex, claude):
                self.assertEqual({name.split('/')[0] for name in archive.namelist()}, {'academyinfo-flow'})
                self.assertIn('academyinfo-flow/SKILL.md', archive.namelist())
                self.assertNotIn('plugin.json', archive.namelist())
                self.assertNotIn('mcp.json', archive.namelist())
                self.assertNotIn('.mcp.json', archive.namelist())
            for relative in installer.REQUIRED_FILES:
                expected = (self.repo / 'skills/academyinfo-flow' / relative).read_bytes()
                self.assertEqual(codex.read('academyinfo-flow/' + relative), expected)
                self.assertEqual(claude.read('academyinfo-flow/' + relative), expected)
            self.assertTrue(all('__pycache__' not in name and '.venv' not in name for archive in (plugin, codex, claude) for name in archive.namelist()))

    def test_codex_skill_archive_extracts_as_installable_folder_with_matching_inventory(self):
        archive = self.build()['codex_skill']
        destination = Path(self.temporary.name) / 'isolated-user-skills'
        with zipfile.ZipFile(archive) as package:
            package.extractall(destination)
        _, expected, _ = installer.validate_source(self.repo)
        self.assertEqual(installer.inventory(destination / 'academyinfo-flow'), expected)

    def test_unchanged_sources_produce_repeatable_archives(self):
        first = {name: hashlib.sha256(path.read_bytes()).hexdigest() for name, path in self.build().items()}
        second = {name: hashlib.sha256(path.read_bytes()).hexdigest() for name, path in self.build().items()}
        self.assertEqual(first, second)

    def test_version_mismatch_and_output_inside_skill_are_rejected(self):
        path = self.repo / '.claude-plugin/plugin.json'
        manifest = json.loads(path.read_text(encoding='utf-8'))
        manifest['version'] = '99.0.0'
        path.write_text(json.dumps(manifest), encoding='utf-8')
        with patch.object(builder, 'ROOT', self.repo), self.assertRaises(ValueError):
            builder.build_all()
        path.write_text((ROOT / '.claude-plugin/plugin.json').read_text(encoding='utf-8'), encoding='utf-8')
        with patch.object(builder, 'ROOT', self.repo), self.assertRaises(ValueError):
            builder.build_skill('claude-web', self.repo / 'skills/academyinfo-flow/accidental.zip')

    def test_mcp_transports_share_one_verified_endpoint_and_manifest_paths_exist(self):
        paths = self.build()
        with zipfile.ZipFile(paths['plugin']) as package:
            portable = json.loads(package.read('mcp.json'))['mcpServers']
            legacy = json.loads(package.read('.mcp.json'))['mcpServers']
            self.assertEqual(set(portable), {'academyinfo-flow'})
            self.assertEqual(set(portable), set(legacy))
            for name, server in portable.items():
                self.assertEqual(server['type'], 'streamable-http')
                self.assertEqual(legacy[name]['type'], 'http')
                self.assertEqual(server['url'], legacy[name]['url'])
                self.assertEqual(server['url'], 'https://h-rules.stoom.win/api/academyinfo/mcp')
            for manifest in ('.codex-plugin/plugin.json', '.claude-plugin/plugin.json'):
                pointer = json.loads(package.read(manifest))['mcpServers']
                self.assertEqual(pointer, './.mcp.json')
                self.assertIn(pointer.removeprefix('./'), package.namelist())

    def test_mcp_endpoint_drift_is_rejected_before_archiving(self):
        path = self.repo / '.mcp.json'
        data = json.loads(path.read_text(encoding='utf-8'))
        data['mcpServers']['academyinfo-flow']['url'] = 'https://example.invalid/different'
        path.write_text(json.dumps(data), encoding='utf-8')
        with patch.object(builder, 'ROOT', self.repo), self.assertRaises(ValueError):
            builder.build_all()
