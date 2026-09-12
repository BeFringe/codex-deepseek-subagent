import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'probes'))
from adjudicate_g4_sibling_admission_live import AdjudicationError
from verify_p7_windows_mutation_outcome import verify_denied_tool


class DenialEvidenceTests(unittest.TestCase):
    def event(self, decision='deny', reason='TASK.WRITER_LEASE_BLOCKED: held claim'):
        return {'stdout': json.dumps({'hookSpecificOutput': {
            'permissionDecision': decision, 'permissionDecisionReason': reason}})}

    def test_denial_requires_no_posttool_observation(self):
        verify_denied_tool(self.event(), [], 'TASK.WRITER_LEASE_BLOCKED')
        with self.assertRaisesRegex(AdjudicationError, 'emitted PostToolUse'):
            verify_denied_tool(self.event(), [{'hook_event_name': 'PostToolUse'}], 'TASK.WRITER_LEASE_BLOCKED')

    def test_matching_reason_without_deny_is_insufficient(self):
        for decision in ('allow', 'ask', None):
            with self.subTest(decision=decision), self.assertRaisesRegex(AdjudicationError, 'explicit PreToolUse denial'):
                verify_denied_tool(self.event(decision), [], 'TASK.WRITER_LEASE_BLOCKED')

    def test_different_guard_failure_does_not_prove_writer_exclusion(self):
        with self.assertRaisesRegex(AdjudicationError, 'authority boundary'):
            verify_denied_tool(self.event(reason='TASK.CONTEXT_LOST'), [], 'TASK.WRITER_LEASE_BLOCKED')


if __name__ == '__main__':
    unittest.main()
