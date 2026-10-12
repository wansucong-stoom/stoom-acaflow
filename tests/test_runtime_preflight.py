"""Offline runtime checks with simulated source responses; no public queries."""
import importlib.util
import json
from pathlib import Path
import subprocess
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

SCRIPT = Path(__file__).resolve().parents[1] / 'skills/academyinfo-flow/scripts/runtime_preflight.py'
spec = importlib.util.spec_from_file_location('test_preflight', SCRIPT)
preflight = importlib.util.module_from_spec(spec)
spec.loader.exec_module(preflight)


class PreflightTests(unittest.TestCase):
    def test_default_only_checks_runtime_without_claiming_source_access(self):
        reader = Mock(side_effect=AssertionError('Unexpected source query'))
        result = preflight.inspect_runtime(scope_reader=reader)
        self.assertTrue(result['ok'])
        self.assertEqual(result['status'], 'runtime_ready_source_unverified')
        self.assertFalse(result['source_access_verified'])
        reader.assert_not_called()

    def test_explicit_source_query_retains_original_public_response(self):
        original = {'status': 'ok', 'complete': True, 'rows': [{'year': '2099'}],
                    'sources': [{'raw_sha256': 'b' * 64, 'synthetic': True}]}
        reader = Mock(return_value={'status': 'ok', 'scope_response': original})
        result = preflight.inspect_runtime(check_source=True, scope_reader=reader)
        self.assertTrue(result['ok'])
        self.assertTrue(result['source_access_verified'])
        self.assertEqual(result['source']['scope_response'], original)
        reader.assert_called_once_with(45)

    def test_source_failure_is_not_promoted_to_ready_or_values_zero(self):
        original = {'status': 'error', 'error': {'code': 'synthetic_source_denied'},
                    'sources': [{'raw_sha256': 'c' * 64}]}
        result = preflight.inspect_runtime(check_source=True,
                    scope_reader=lambda _: {'status': 'error', 'scope_response': original})
        self.assertFalse(result['ok'])
        self.assertEqual(result['status'], 'blocked')
        self.assertEqual(result['source']['scope_response'], original)

    def test_old_python_does_not_attempt_source(self):
        reader = Mock()
        with patch.object(preflight.sys, 'version_info', (3, 10, 1)):
            result = preflight.inspect_runtime(check_source=True, scope_reader=reader)
        self.assertFalse(result['ok'])
        self.assertEqual(result['source']['status'], 'not_attempted')
        reader.assert_not_called()

    def test_pdf_dependency_is_optional_and_requires_supported_version_when_requested(self):
        for version, expected in (('0.9.0', False), ('0.11.4', True), ('1.0.0', False), ('0.11.0rc1', False)):
            with self.subTest(version=version), patch.object(preflight.importlib.metadata, 'version', return_value=version), patch.object(preflight.importlib.util, 'find_spec', return_value=object()):
                result = preflight.inspect_runtime(require_pdf=True)
                self.assertEqual(result['ok'], expected)
                self.assertEqual(result['pdf']['available'], expected)
                self.assertTrue(preflight.inspect_runtime()['ok'])

    def test_scope_timeout_and_unparseable_response_do_not_echo_stderr(self):
        with patch.object(preflight.subprocess, 'run', side_effect=subprocess.TimeoutExpired('scope', 1)):
            self.assertEqual(preflight._scope(1)['reason'], 'source_timeout')
        with patch.object(preflight.subprocess, 'run', return_value=SimpleNamespace(returncode=1, stdout='<html>failure</html>', stderr='private-runtime-value')):
            result = preflight._scope(1)
            self.assertEqual(result['status'], 'error')
            self.assertNotIn('private-runtime-value', json.dumps(result))

    def test_scope_incomplete_success_label_is_not_verified(self):
        original = {'status': 'ok', 'complete': False, 'rows': [], 'sources': []}
        with patch.object(preflight.subprocess, 'run', return_value=SimpleNamespace(returncode=0, stdout=json.dumps(original), stderr='')):
            result = preflight._scope(1)
        self.assertEqual(result['status'], 'error')
        self.assertEqual(result['scope_response'], original)
