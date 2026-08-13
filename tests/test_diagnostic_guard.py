import importlib.util
from pathlib import Path
import sys
import unittest


REPO = Path(__file__).resolve().parents[1]


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


diagnostic_guard = load_module(
    "diagnostic_guard", REPO / "hooks" / "diagnostic_guard.py"
)


class DiagnosticGuardTests(unittest.TestCase):
    def setUp(self):
        self.contract = {
            "posture": "strict_read_only",
            "review_range": {"base_oid": "a" * 40, "head_oid": "b" * 40},
            "required_invariants": ["state transition remains fail-closed"],
            "diagnostics": {
                "stable_failure_codes": ["OWNER.QUERY_FAILED"],
                "known_true_failure_codes": ["OWNER.QUERY_FAILED"],
                "generic_unclassified_failure_code": "TASK.FAILURE_UNCLASSIFIED",
                "allow_literal_expensive_rerun": False,
            },
            "proven_input_baselines": [
                {
                    "baseline_id": "local-replay-v1",
                    "owner": "fixture.owner",
                    "manifest_path": "inputs/replay.json",
                    "sha256": "c" * 64,
                    "proven_failure_code": "OWNER.QUERY_FAILED",
                    "non_authorizing": True,
                    "replay_policy": "reuse_without_authority_expansion",
                }
            ],
        }

    def test_stable_owner_failure_code_is_preserved(self):
        result = diagnostic_guard.classify_owner_failure(
            self.contract, "OWNER.QUERY_FAILED"
        )

        self.assertEqual(result["returned_failure_code"], "OWNER.QUERY_FAILED")
        self.assertFalse(result["used_generic_fallback"])

    def test_only_unclassified_failure_uses_generic_code(self):
        unknown = diagnostic_guard.classify_owner_failure(self.contract, "WRAPPER.UNKNOWN")
        missing = diagnostic_guard.classify_owner_failure(self.contract, None)

        self.assertEqual(unknown["returned_failure_code"], "TASK.FAILURE_UNCLASSIFIED")
        self.assertEqual(missing["returned_failure_code"], "TASK.FAILURE_UNCLASSIFIED")
        self.assertTrue(unknown["used_generic_fallback"])

    def test_literal_expensive_rerun_requires_explicit_authority(self):
        with self.assertRaisesRegex(
            diagnostic_guard.DiagnosticViolation, "not authorized"
        ):
            diagnostic_guard.require_literal_rerun_authority(self.contract)

    def test_replay_baseline_remains_non_authorizing_evidence(self):
        reference = diagnostic_guard.baseline_reference(
            self.contract, "local-replay-v1"
        )

        self.assertTrue(reference["non_authorizing"])
        self.assertNotIn("owned_paths", reference)
        self.assertNotIn("git_authority", reference)
        self.assertNotIn("completion", reference)


if __name__ == "__main__":
    unittest.main()
