import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import unittest


REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "probes" / "check_mutation_surfaces.py"
MATRIX = REPO / "probes" / "codex-0.148.0-alpha.9-mutation-surfaces.json"
HISTORICAL_MATRIX = REPO / "probes" / "codex-0.147.0-mutation-surfaces.json"


SPEC = importlib.util.spec_from_file_location("check_mutation_surfaces", SCRIPT)
check_mutation_surfaces = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(check_mutation_surfaces)


class MutationSurfaceMatrixTests(unittest.TestCase):
    def test_matrix_is_complete_and_keeps_direct_write_unqualified(self):
        matrix = check_mutation_surfaces.load_matrix(MATRIX)
        result = check_mutation_surfaces.qualification(matrix)

        self.assertFalse(result["direct_write_qualified"])
        blocker_ids = {blocker["id"] for blocker in result["blockers"]}
        self.assertIn("write_stdin", blocker_ids)
        self.assertIn("shell", blocker_ids)
        self.assertIn("mcp", blocker_ids)
        self.assertIn("extension_freeform", blocker_ids)
        self.assertIn("extension_function", blocker_ids)
        self.assertIn("codex_config_mutation", blocker_ids)
        self.assertIn("authority_escalation", blocker_ids)

    def test_historical_schema_one_matrix_remains_replayable(self):
        matrix = check_mutation_surfaces.load_matrix(HISTORICAL_MATRIX)

        self.assertEqual(matrix["codex_version"], "0.147.0")
        self.assertFalse(
            check_mutation_surfaces.qualification(matrix)["direct_write_qualified"]
        )

    def test_require_qualified_fails_closed(self):
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "--matrix", str(MATRIX), "--require-qualified"],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )

        self.assertEqual(result.returncode, 2, result.stderr)
        output = json.loads(result.stdout)
        self.assertTrue(output["valid"])
        self.assertFalse(output["direct_write_qualified"])

    def test_source_anchor_drift_invalidates_matrix(self):
        matrix = check_mutation_surfaces.load_matrix(MATRIX)
        failures = check_mutation_surfaces.verify_anchors(matrix, Path(__file__).parent)

        self.assertTrue(failures)


if __name__ == "__main__":
    unittest.main()
