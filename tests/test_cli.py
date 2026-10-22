"""Offline CLI, school-scoped engine, and installed-wheel regressions."""
from contextlib import redirect_stdout, redirect_stderr
import copy
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch
import zipfile

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / 'skills/academyinfo-flow/scripts'
sys.path.insert(0, str(SCRIPTS))
import live_json
import live_report
import route_registry
import runtime_preflight
from test_live_report import FakeViewerClient, CATALOG_URL, command

SPEC = importlib.util.spec_from_file_location('test_flow_cli', SCRIPTS / 'academyinfo_live.py')
cli = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(cli)


def catalog_result(rows=None):
    return {'status': 'ok', 'complete': True, 'rows': rows if rows is not None else [
        {'item_id': '1', 'pgm_estn_nm': '7-가. Synthetic disclosure fixture'}],
        'sources': [{'source_url': CATALOG_URL, 'raw_sha256': 'a' * 64,
                     'retrieved_utc': '2026-10-20T00:00:00+00:00'}]}


class CliTests(unittest.TestCase):
    def setUp(self):
        temporary_root = ROOT / '.test-tmp'
        temporary_root.mkdir(exist_ok=True)
        self.temporary = tempfile.TemporaryDirectory(dir=temporary_root)
        self.addCleanup(self.temporary.cleanup)
        self.folder = Path(self.temporary.name)
        self.client = FakeViewerClient(1, {})
        self.observer = Mock(return_value={'recorded': False, 'route_count': 0})
        self.observer_patch = patch.object(route_registry, 'observe_result', self.observer)
        self.observer_patch.start()
        self.addCleanup(self.observer_patch.stop)

    def invoke(self, argv):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = cli.main(argv)
        return code, json.loads(out.getvalue()), err.getvalue()

    @staticmethod
    def selection(query):
        if query['command'] == 'scope':
            return {'status': 'ok', 'complete': True, 'data': {'years': ['2026']},
                    'sources': [{'source_url': 'https://m.academyinfo.go.kr/main/main0780/selectListLink.do'}]}
        return catalog_result()

    def report_args(self, *extra):
        return ['report', '--year', '2026', '--division', '02', '--item', '7-가',
                '--level', 'department', '--limit', '100', *extra]

    def test_doctor_is_offline_and_does_not_record_a_route(self):
        with patch('urllib.request.OpenerDirector.open', side_effect=AssertionError('unexpected network')), \
                patch.object(runtime_preflight, '_scope', side_effect=AssertionError('unexpected source check')):
            code, result, _ = self.invoke(['doctor'])
        self.assertEqual(code, 0)
        self.assertTrue(result['complete'])
        self.assertEqual(result['source']['status'], 'not_checked')
        self.observer.assert_not_called()

    def test_human_item_code_resolves_fresh_catalog_and_observes_once_after_validation(self):
        with patch.object(live_json, 'run_command', side_effect=self.selection) as selection, \
                patch.object(live_report, 'ViewerDataClient', return_value=self.client):
            code, result, events = self.invoke(self.report_args('--progress'))
        self.assertEqual(code, 0, result)
        self.assertEqual(result['item_resolution']['resolved_item'], '1')
        self.assertEqual(result['item_resolution']['source'], 'fresh_catalog')
        self.assertEqual(self.client.start_calls[0][2], '1')
        self.assertEqual([call.args[0]['command'] for call in selection.call_args_list], ['scope', 'catalog'])
        self.observer.assert_called_once()
        observed = self.observer.call_args.args[0]
        self.assertIn('selection_validation_sources', observed)
        self.assertEqual(observed['item_resolution']['requested_code'], '7-가')
        self.assertNotIn('cell_sources', result['rows'][0])
        self.assertEqual(json.loads(events.splitlines()[-1])['exit_code'], 0)

    def test_ambiguous_code_and_unpublished_year_fail_before_report_initialization(self):
        for failure in ('ambiguous', 'unpublished'):
            def selection(query):
                if failure == 'unpublished':
                    return {'status': 'ok', 'complete': True, 'data': {'years': ['2025']}, 'sources': []}
                if query['command'] == 'scope':
                    return self.selection(query)
                return catalog_result([{'item_id': n, 'pgm_estn_nm': '7-가. Synthetic fixture'} for n in ('1', '2')])
            with self.subTest(failure=failure), patch.object(live_json, 'run_command', side_effect=selection), \
                    patch.object(live_report, 'ViewerDataClient') as factory:
                code, result, _ = self.invoke(self.report_args())
                self.assertEqual(code, 2)
                self.assertFalse(result['complete'])
                self.assertIn(result['error']['code'], {'item_code_unresolved', 'year_not_published'})
                factory.assert_not_called()

    def test_partial_and_source_error_have_distinct_exits(self):
        self.client.config['fail_page'] = 2
        with patch.object(live_json, 'run_command', side_effect=self.selection), \
                patch.object(live_report, 'ViewerDataClient', return_value=self.client):
            code, result, _ = self.invoke(self.report_args())
        self.assertEqual(code, 3)
        self.assertEqual(result['status'], 'partial')
        self.assertFalse(result['complete'])
        with patch.object(live_json, 'run_command', return_value={'status': 'error', 'complete': False,
                'rows': [], 'error': {'code': 'source_unavailable'}}):
            code, result, _ = self.invoke(self.report_args())
        self.assertEqual(code, 2)
        self.assertEqual(result['error']['code'], 'source_unavailable')

    def test_route_observation_failure_does_not_change_statistical_success(self):
        self.observer.side_effect = OSError('PRIVATE_STATE_PATH')
        with patch.object(live_json, 'run_command', return_value={'command': 'scope', 'status': 'ok',
                'complete': True, 'data': {'years': ['2026']}, 'rows': []}):
            code, result, _ = self.invoke(['scope'])
        self.assertEqual(code, 0)
        self.assertTrue(result['complete'])
        self.assertFalse(result['route_registry']['recorded'])
        self.assertNotIn('PRIVATE_STATE_PATH', json.dumps(result))
        self.observer.assert_called_once()

    def test_existing_output_is_protected_before_lookup_and_force_writes_valid_json(self):
        target = self.folder / 'result.json'
        target.write_text('keep existing data', encoding='utf-8')
        with patch.object(cli, 'execute') as execute:
            code, result, _ = self.invoke(['scope', '--output', str(target)])
        self.assertEqual(code, 2)
        self.assertEqual(result['error']['code'], 'invalid_input')
        self.assertEqual(target.read_text(encoding='utf-8'), 'keep existing data')
        execute.assert_not_called()
        expected = {'status': 'ok', 'complete': True, 'command': 'scope', 'rows': []}
        with patch.object(cli, 'execute', return_value=copy.deepcopy(expected)):
            code, summary, _ = self.invoke(['scope', '--output', str(target), '--force'])
        self.assertEqual(code, 0)
        self.assertEqual(summary['output_file'], str(target))
        self.assertTrue(json.loads(target.read_text(encoding='utf-8'))['complete'])

    def test_source_cancellation_does_not_create_output_or_expose_runtime_details(self):
        target = self.folder / 'cancelled.json'
        with patch.object(cli, 'execute', side_effect=KeyboardInterrupt):
            code, result, _ = self.invoke(['scope', '--output', str(target)])
        self.assertEqual(code, 130)
        self.assertEqual(result['error']['code'], 'interrupted')
        self.assertFalse(target.exists())
        self.observer.assert_not_called()
        with patch.object(cli, 'execute', side_effect=RuntimeError('PRIVATE_RUNTIME_SECRET')):
            code, result, _ = self.invoke(['scope'])
        self.assertEqual(code, 2)
        self.assertNotIn('PRIVATE_RUNTIME_SECRET', json.dumps(result))

    def test_cancelled_or_failed_output_write_preserves_existing_json_and_cleans_temporary(self):
        target = self.folder / 'result.json'
        target.write_text('{"preserved":true}', encoding='utf-8')
        for failure, expected_code in ((KeyboardInterrupt, 130), (OSError('PRIVATE_WRITE_DETAILS'), 2)):
            with self.subTest(failure=failure), patch.object(cli, 'execute', return_value={
                    'status': 'ok', 'complete': True, 'rows': []}), patch.object(cli.os, 'fsync', side_effect=failure):
                code, result, _ = self.invoke(['scope', '--output', str(target), '--force'])
            self.assertEqual(code, expected_code)
            self.assertEqual(target.read_text(encoding='utf-8'), '{"preserved":true}')
            self.assertEqual(list(self.folder.glob('.academyinfo-output-*.tmp')), [])
            self.assertNotIn('PRIVATE_WRITE_DETAILS', json.dumps(result))

    def test_exclusive_output_commit_does_not_replace_a_racing_target(self):
        target = self.folder / 'racing.json'
        original_fsync = cli.os.fsync
        def raced(handle):
            target.write_text('created by another writer', encoding='utf-8')
            original_fsync(handle)
        with patch.object(cli, 'execute', return_value={'status': 'ok', 'complete': True, 'rows': []}), \
                patch.object(cli.os, 'fsync', side_effect=raced):
            code, _, _ = self.invoke(['scope', '--output', str(target)])
        self.assertEqual(code, 2)
        self.assertEqual(target.read_text(encoding='utf-8'), 'created by another writer')
        self.assertEqual(list(self.folder.glob('.academyinfo-output-*.tmp')), [])

    def test_batch_route_observation_runs_once_on_the_final_result(self):
        batch = {'command': 'batch', 'status': 'ok', 'complete': True, 'results': [], 'rows': []}
        with patch.object(cli, 'execute', return_value=batch):
            code, result, _ = self.invoke(['batch', '--input', 'synthetic.json'])
        self.assertEqual(code, 0)
        self.observer.assert_called_once_with(result)


class SchoolScopeTests(unittest.TestCase):
    class SchoolViewer(FakeViewerClient):
        def start_report(self, year, division, item, *, level, school_code=None):
            self.received_school_code = school_code
            return super().start_report(year, division, item, level=level)

    def test_school_form_preserves_real_identity_and_is_not_reused_for_another_name(self):
        client = self.SchoolViewer(1, {})
        registry_exchange = client.exchange(b'{}', url='https://m.academyinfo.go.kr/intro/intro0350/selectSchlListAll.do')
        with patch.object(live_report, 'ViewerDataClient', return_value=client), \
                patch.object(live_report, 'iter_schools', return_value=[registry_exchange]) as registry_calls, \
                patch.object(live_report, 'school_rows', return_value=[{
                    'schl_id': '0000001', 'schl_nm': '시험대학 0', 'schl_div_cd': '02'}]), \
                live_report.ReportBatch() as batch:
            valid = live_report.run_command(command(school_code='0000001', school_names=['시험대학 0']), batch=batch)
            self.assertTrue(valid['complete'], valid)
            self.assertEqual(client.received_school_code, '0000001')
            self.assertEqual(valid['source_scope']['form'], '60')
            self.assertEqual(valid['source_scope']['school_name'], '시험대학 0')
            self.assertEqual(valid['selectors']['formClassification'], '60')
            # That name is present on the report's second page but is not the
            # requested code's current registry identity. A warmed snapshot
            # must not allow it to bypass the school identity check.
            invalid = live_report.run_command(command(school_code='0000001', school_names=['시험대학 2']), batch=batch)
            self.assertFalse(invalid['complete'])
            self.assertEqual(invalid['error']['code'], 'invalid_input')
            self.assertEqual(invalid['rows'], [])
            self.assertEqual(len(client.start_calls), 1)
            self.assertEqual(registry_calls.call_count, 2)

    def test_school_code_requires_one_name_and_department_scope(self):
        for override in ({'level': 'school', 'school_names': ['시험대학 0']},
                         {'school_names': []}, {'school_names': ['시험대학 0', '시험대학 1']},
                         {'school_code': 'malformed', 'school_names': ['시험대학 0']}):
            with self.subTest(override=override), patch.object(live_report, 'ViewerDataClient') as factory:
                result = live_report.run_command(command(**{'school_code': '0000001', **override}))
                self.assertEqual(result['error']['code'], 'invalid_input')
                factory.assert_not_called()


class WheelTests(unittest.TestCase):
    def test_wheel_imports_work_without_source_tree_or_top_level_sibling_modules(self):
        temporary_root = ROOT / '.test-tmp'
        temporary_root.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=temporary_root) as directory:
            folder = Path(directory)
            source = folder / 'source'
            source.mkdir()
            for name in ('pyproject.toml', 'LICENSE'):
                shutil.copyfile(ROOT / name, source / name)
            shutil.copytree(ROOT / 'skills', source / 'skills', ignore=shutil.ignore_patterns('__pycache__'))
            wheels = folder / 'wheels'
            wheels.mkdir()
            build = subprocess.run([sys.executable, '-B', '-c',
                'from setuptools.build_meta import build_wheel; import sys; build_wheel(sys.argv[1])', str(wheels)],
                cwd=source, capture_output=True, text=True, encoding='utf-8', timeout=90)
            self.assertEqual(build.returncode, 0, build.stderr)
            wheel = next(wheels.glob('*.whl'))
            installed = folder / 'installed'
            with zipfile.ZipFile(wheel) as package:
                package.extractall(installed)
            script = '''import importlib,json,sys
sys.path.insert(0,sys.argv[1])
from academyinfo_live import academyinfo_live as cli
from academyinfo_live import live_batch,live_guide,route_registry
report=cli._module('live_report')
assert report.__name__ == 'academyinfo_live.live_report'
assert report.ViewerDataClient.__module__.startswith('academyinfo_live.vendor.')
assert live_batch.live_report is report
assert live_guide.NAVIGATION_PATH.is_file()
assert route_registry.SEED.is_file()
assert 'live_json' not in sys.modules
assert 'live_report' not in sys.modules
raise SystemExit(cli.main(['doctor']))
'''
            checked = subprocess.run([sys.executable, '-B', '-I', '-c', script, str(installed)],
                cwd=folder, capture_output=True, text=True, encoding='utf-8', timeout=30)
            self.assertEqual(checked.returncode, 0, checked.stderr)
            self.assertTrue(json.loads(checked.stdout)['complete'])
            module = subprocess.run([sys.executable, '-B', '-I', '-c',
                'import runpy,sys;sys.path.insert(0,sys.argv[1]);sys.argv=["academyinfo_live","--version"];runpy.run_module("academyinfo_live",run_name="__main__")',
                str(installed)], cwd=folder, capture_output=True, text=True, encoding='utf-8', timeout=30)
            self.assertEqual(module.returncode, 0, module.stderr)
            self.assertEqual(module.stdout.strip(), '0.3.2')


if __name__ == '__main__':
    unittest.main()
