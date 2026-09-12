import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'probes'))
from run_p7_windows_mutation import invocation, negative_authority


class WindowsMutationPreparationTests(unittest.TestCase):
    def test_negative_contract_never_grants_foreign_write_authority(self):
        original = {'assignment_mutation_mode': 'write', 'owned_paths': ['qualified.txt'],
                    'excluded_paths': [], 'git_authority': {'stage': False, 'commit': False}}
        authority = negative_authority(original)
        self.assertEqual(authority['assignment_mutation_mode'], 'write')
        self.assertEqual(authority['owned_paths'], ['qualified.txt'])
        self.assertEqual(authority['excluded_paths'], [])
        self.assertNotIn('foreign.txt', authority['owned_paths'])
        self.assertEqual(authority, original)
        self.assertEqual(original['excluded_paths'], [])
        self.assertFalse(any(authority['git_authority'].values()))
        with self.assertRaises(RuntimeError):
            negative_authority(dict(original, owned_paths=['foreign.txt']))

    def test_mutation_cases_enable_windows_sandbox_and_retain_parent_route(self):
        for case in ('capability', 'positive', 'negative'):
            args = invocation(Path('candidate.exe'), Path('fixture root'), Path('role.toml'),
                              'deepseek', Path('private catalog.json'), case)
            self.assertEqual(args[args.index('-s') + 1],
                             'read-only' if case == 'capability' else 'workspace-write')
            settings = dict(args[index + 1].split('=', 1) for index, value in enumerate(args) if value == '-c')
            self.assertEqual(json.loads(settings['model_provider']), 'openai')
            if case != 'capability':
                self.assertEqual(json.loads(settings['windows.sandbox']), 'unelevated')
            else:
                self.assertNotIn('windows.sandbox', settings)
            self.assertEqual(json.loads(settings['model_catalog_json']), 'private catalog.json')
            self.assertFalse(json.loads(settings['features.code_mode_host']))
            self.assertFalse(json.loads(settings['model_providers.deepseek.supports_namespace_tools']))
            self.assertTrue(json.loads(settings['model_providers.deepseek.requires_function_call_output_adjacency']))
            self.assertIn('--ignore-user-config', args)
            self.assertIn('--ignore-rules', args)
            self.assertNotIn('--dangerously-bypass-approvals-and-sandbox', args)
