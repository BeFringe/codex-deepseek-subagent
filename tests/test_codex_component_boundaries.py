import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "probes" / "check_codex_component_boundaries.py"

SPEC = importlib.util.spec_from_file_location("check_codex_component_boundaries", SCRIPT)
check_codex_component_boundaries = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(check_codex_component_boundaries)

RELEASE_INDEX = check_codex_component_boundaries.load_index()
CURRENT_RUNTIME = check_codex_component_boundaries.runtime_identity(RELEASE_INDEX)
CONTRACT = check_codex_component_boundaries.evidence_path(
    RELEASE_INDEX, "component_boundaries"
)


class CodexComponentBoundaryTests(unittest.TestCase):
    def test_current_runtime_contract_is_exact_and_fail_closed(self):
        contract = check_codex_component_boundaries.load_contract(CONTRACT)
        result = check_codex_component_boundaries.qualification(contract)

        self.assertEqual(RELEASE_INDEX["current_runtime_role"], "current_signed_runtime")
        self.assertEqual(contract["codex_version"], CURRENT_RUNTIME["codex_version"])
        self.assertEqual(contract["source_commit"], CURRENT_RUNTIME["source_commit"])
        self.assertTrue(result["source_visibility_improved"])
        self.assertTrue(result["isolated_probe_harness_feasible"])
        self.assertFalse(result["native_heterogeneous_child_restored"])
        self.assertFalse(result["pretool_plaintext_assignment_visible"])
        self.assertFalse(result["per_child_provider_override_available"])
        self.assertFalse(result["app_server_thread_is_native_child_equivalent"])
        self.assertFalse(result["phase1_complete"])
        self.assertFalse(result["direct_write_qualified"])
        self.assertEqual(result["phase2_state"], "closed")
        self.assertEqual(result["phase3_state"], "closed")

    def test_source_anchors_and_negative_anchors_are_checked(self):
        contract = check_codex_component_boundaries.load_contract(CONTRACT)
        with tempfile.TemporaryDirectory() as temp_dir:
            source_root = Path(temp_dir)
            for anchor in contract["anchors"]:
                path = source_root / anchor["path"]
                path.parent.mkdir(parents=True, exist_ok=True)
                with path.open("a", encoding="utf-8") as stream:
                    stream.write(anchor["contains"] + "\n")

            with mock.patch.object(
                check_codex_component_boundaries,
                "_git_identity",
                return_value=(source_root, contract["source_commit"], []),
            ):
                observed, failures = check_codex_component_boundaries.verify_source(
                    contract, source_root
                )
            self.assertEqual(observed, contract["source_commit"])
            self.assertEqual(failures, [])

            protocol = source_root / "codex-rs/app-server-protocol/src/protocol/common.rs"
            with protocol.open("a", encoding="utf-8") as stream:
                stream.write("collaboration/spawn\n")
            with mock.patch.object(
                check_codex_component_boundaries,
                "_git_identity",
                return_value=(source_root, contract["source_commit"], []),
            ):
                _, failures = check_codex_component_boundaries.verify_source(
                    contract, source_root
                )
            self.assertIn(
                "forbidden source anchor found: app_server_has_no_native_spawn_rpc",
                failures,
            )

    def test_promoted_verdict_is_rejected(self):
        contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
        contract["verdict"]["native_heterogeneous_child_restored"] = True
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "contract.json"
            path.write_text(json.dumps(contract), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "cannot promote"):
                check_codex_component_boundaries.load_contract(path)


if __name__ == "__main__":
    unittest.main()
