import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "probes" / "check_runtime_evidence_index.py"

SPEC = importlib.util.spec_from_file_location("check_runtime_evidence_index", SCRIPT)
runtime_evidence = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(runtime_evidence)


class RuntimeEvidenceIndexTests(unittest.TestCase):
    def write_index(self, value: dict, directory: str) -> Path:
        path = Path(directory) / "runtime-index.json"
        path.write_text(json.dumps(value), encoding="utf-8")
        return path

    def test_current_semantic_role_resolves_to_exact_consistent_evidence(self):
        result = runtime_evidence.qualification()

        self.assertTrue(result["valid"])
        self.assertEqual(result["current_runtime_role"], "current_signed_runtime")
        self.assertTrue(result["codex_version"])
        self.assertRegex(result["source_commit"], r"^[0-9a-f]{40}$")
        self.assertEqual(result["evidence_failures"], [])

    def test_current_role_cannot_be_silently_reassigned(self):
        value = json.loads(runtime_evidence.DEFAULT_INDEX.read_text(encoding="utf-8"))
        value["current_runtime_role"] = "prior_signed_runtime"

        with tempfile.TemporaryDirectory() as directory:
            path = self.write_index(value, directory)
            with self.assertRaisesRegex(ValueError, "current signed runtime"):
                runtime_evidence.load_index(path)

    def test_duplicate_exact_identity_under_two_roles_is_rejected(self):
        value = copy.deepcopy(
            json.loads(runtime_evidence.DEFAULT_INDEX.read_text(encoding="utf-8"))
        )
        value["runtime_roles"]["schema_replay_runtime"] = value["runtime_roles"][
            "migration_handoff_runtime"
        ]

        with tempfile.TemporaryDirectory() as directory:
            path = self.write_index(value, directory)
            with self.assertRaisesRegex(ValueError, "same identity"):
                runtime_evidence.load_index(path)


if __name__ == "__main__":
    unittest.main()
