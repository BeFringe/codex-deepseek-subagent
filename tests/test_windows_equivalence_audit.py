import importlib.util
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'probes'))
from run_p7_windows_provider_free import equivalence_cases


class WindowsEquivalenceAuditTests(unittest.TestCase):
    def test_missing_skipped_failed_or_non_windows_execution_cannot_close_a_case(self):
        previous = {'test_id': 'test_plaintext_handoff.Original.test_race',
                    'classification': {'category': 'b'}}
        baseline = {'cases': [previous]}
        for status in ('skipped', 'failed', 'error'):
            actual = dict(previous, status=status, events=[])
            self.assertFalse(equivalence_cases(baseline, [actual], platform='win32')[0]['windows_equivalence_proven'])
        self.assertFalse(equivalence_cases(baseline, [], platform='win32')[0]['windows_equivalence_proven'])
        actual = dict(previous, status='passed', events=[])
        self.assertFalse(equivalence_cases(baseline, [actual], platform='darwin')[0]['windows_equivalence_proven'])
        self.assertTrue(equivalence_cases(baseline, [actual], platform='win32')[0]['windows_equivalence_proven'])

    def test_equivalent_backend_is_case_exact_and_records_executable_source(self):
        previous = {'test_id': 'test_plaintext_candidate_wrapper.Original.test_ceiling',
                    'classification': {'category': 'b'}}
        result = equivalence_cases({'cases': [previous]},
                                   [dict(previous, status='passed', events=[])], platform='win32')[0]
        self.assertEqual(result['baseline_test_id'], result['executed_test_id'])
        self.assertEqual(result['backend'], 'windows_native_launcher')
        self.assertIn('probes/windows_candidate_launcher.py', result['source_paths'])
