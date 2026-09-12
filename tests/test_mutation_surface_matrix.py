import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "probes" / "check_mutation_surfaces.py"
PREVIOUS_MATRIX = REPO / "probes" / "codex-0.150.0-alpha.8-mutation-surfaces.json"
LEGACY_ALPHA_MATRIX = REPO / "probes" / "codex-0.148.0-alpha.15-mutation-surfaces.json"
HISTORICAL_MATRIX = REPO / "probes" / "codex-0.147.0-mutation-surfaces.json"


SPEC = importlib.util.spec_from_file_location("check_mutation_surfaces", SCRIPT)
check_mutation_surfaces = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(check_mutation_surfaces)

RELEASE_INDEX = check_mutation_surfaces.load_index()
MATRIX = check_mutation_surfaces.evidence_path(RELEASE_INDEX, "mutation_surfaces")


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
        self.assertIn("plugin_metrics_sidecar", blocker_ids)
        self.assertIn("accepted_result_evidence", blocker_ids)
        self.assertIn("appserver_host_control_bootstrap", blocker_ids)

    def test_appserver_bootstrap_is_a_cross_surface_escape_not_a_native_tool(self):
        matrix = check_mutation_surfaces.load_matrix(MATRIX)
        surface = next(
            item
            for item in matrix["surfaces"]
            if item["id"] == "appserver_host_control_bootstrap"
        )

        self.assertEqual(matrix["schema"], 4)
        self.assertTrue(surface["mutation_capable"])
        self.assertEqual(
            surface["pre_tool_use"], "outer-surface-only-no-per-rpc-child-hook"
        )
        self.assertIsNone(surface["canonical_hook_name"])
        self.assertFalse(surface["semantically_constrainable"])
        self.assertEqual(
            surface["decision"], "block-from-external-worker-or-os-confine"
        )

    def test_historical_schema_one_matrix_remains_replayable(self):
        matrix = check_mutation_surfaces.load_matrix(HISTORICAL_MATRIX)

        self.assertEqual(matrix["codex_version"], "0.147.0")
        self.assertFalse(
            check_mutation_surfaces.qualification(matrix)["direct_write_qualified"]
        )

    def test_prior_signed_runtime_matrix_remains_replayable(self):
        matrix = check_mutation_surfaces.load_matrix(PREVIOUS_MATRIX)
        prior = check_mutation_surfaces.runtime_identity(
            RELEASE_INDEX, "prior_signed_runtime"
        )

        self.assertEqual(matrix["codex_version"], prior["codex_version"])
        self.assertEqual(matrix["source_commit"], prior["source_commit"])
        self.assertFalse(
            check_mutation_surfaces.qualification(matrix)["direct_write_qualified"]
        )

    def test_legacy_alpha_matrix_remains_replayable(self):
        matrix = check_mutation_surfaces.load_matrix(LEGACY_ALPHA_MATRIX)

        self.assertEqual(matrix["codex_version"], "0.148.0-alpha.15")
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

    def test_source_identity_requires_exact_matrix_commit(self):
        matrix = check_mutation_surfaces.load_matrix(MATRIX)
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory)
            subprocess.run(["git", "init", "-q", str(source)], check=True)
            subprocess.run(
                ["git", "-C", str(source), "config", "user.email", "probe@example.invalid"],
                check=True,
            )
            subprocess.run(
                ["git", "-C", str(source), "config", "user.name", "Probe"],
                check=True,
            )
            (source / "anchor.txt").write_text("anchor\n", encoding="utf-8")
            subprocess.run(["git", "-C", str(source), "add", "anchor.txt"], check=True)
            subprocess.run(
                ["git", "-C", str(source), "commit", "-q", "-m", "anchor"],
                check=True,
            )
            head = subprocess.run(
                ["git", "-C", str(source), "rev-parse", "HEAD"],
                text=True,
                stdout=subprocess.PIPE,
                check=True,
            ).stdout.strip()

            exact = dict(matrix, source_commit=head)
            self.assertEqual(
                check_mutation_surfaces.verify_source_identity(exact, source),
                [],
            )
            failures = check_mutation_surfaces.verify_source_identity(matrix, source)
            self.assertEqual(len(failures), 1)
            self.assertIn("does not match", failures[0])

    def test_source_identity_rejects_nested_checkout_path(self):
        matrix = check_mutation_surfaces.load_matrix(MATRIX)
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory)
            subprocess.run(["git", "init", "-q", str(source)], check=True)
            nested = source / "nested"
            nested.mkdir()

            failures = check_mutation_surfaces.verify_source_identity(matrix, nested)

            self.assertTrue(
                any("not the exact Git top level" in failure for failure in failures)
            )


if __name__ == "__main__":
    unittest.main()
