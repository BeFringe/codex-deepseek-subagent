import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "probes" / "check_appserver_host_control.py"

SPEC = importlib.util.spec_from_file_location("check_appserver_host_control", SCRIPT)
host_control = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(host_control)

RELEASE_INDEX = host_control.load_index()
CONTRACT = host_control.evidence_path(RELEASE_INDEX, "appserver_host_control")
MUTATION_MATRIX = host_control.evidence_path(RELEASE_INDEX, "mutation_surfaces")


class AppServerHostControlTests(unittest.TestCase):
    def test_contract_is_visible_but_fail_closed(self):
        contract = host_control.load_contract(CONTRACT)
        result = host_control.qualification(contract)

        self.assertTrue(result["host_control_mutation_surface_visible"])
        self.assertFalse(result["native_child_reachability_proven"])
        self.assertFalse(result["pretooluse_child_mediation_proven"])
        self.assertFalse(result["same_uid_client_trust_proven"])
        self.assertFalse(result["may_count_as_child_mutation_qualification"])
        self.assertTrue(result["isolated_client_trust_probe_required"])
        self.assertFalse(result["phase1_complete"])
        self.assertFalse(result["direct_write_qualified"])

    def test_host_control_rpcs_are_not_misclassified_as_native_child_tools(self):
        contract = host_control.load_contract(CONTRACT)
        matrix = json.loads(MUTATION_MATRIX.read_text(encoding="utf-8"))
        surface_ids = {surface["id"] for surface in matrix["surfaces"]}

        self.assertFalse(contract["boundary"]["native_child_tool_surface"])
        self.assertIn("appserver_host_control_bootstrap", surface_ids)
        self.assertNotIn("appserver_host_control_filesystem_rpc", surface_ids)
        self.assertNotIn("appserver_host_control_process_rpc", surface_ids)
        self.assertNotIn("appserver_host_control_command_rpc", surface_ids)

    def test_source_anchors_and_negative_anchors_are_checked(self):
        contract = host_control.load_contract(CONTRACT)
        with tempfile.TemporaryDirectory() as temp_dir:
            source_root = Path(temp_dir)
            for anchor in contract["anchors"]:
                path = source_root / anchor["path"]
                path.parent.mkdir(parents=True, exist_ok=True)
                with path.open("a", encoding="utf-8") as stream:
                    stream.write(anchor["contains"] + "\n")

            with mock.patch.object(
                host_control,
                "_git_identity",
                return_value=(source_root, contract["source_commit"], []),
            ):
                observed, failures = host_control.verify_source(contract, source_root)
            self.assertEqual(observed, contract["source_commit"])
            self.assertEqual(failures, [])

            process = source_root / "codex-rs/app-server-protocol/src/protocol/v2/process.rs"
            with process.open("a", encoding="utf-8") as stream:
                stream.write("thread_id\n")
            with mock.patch.object(
                host_control,
                "_git_identity",
                return_value=(source_root, contract["source_commit"], []),
            ):
                _, failures = host_control.verify_source(contract, source_root)
            self.assertIn(
                "forbidden source anchor found: process_params_have_no_thread_identity",
                failures,
            )

    def test_promoted_reachability_is_rejected(self):
        contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
        contract["verdict"]["native_child_reachability_proven"] = True
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "contract.json"
            path.write_text(json.dumps(contract), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "cannot promote"):
                host_control.load_contract(path)

    def test_confinement_drift_is_rejected(self):
        contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
        contract["families"]["filesystem"]["execution_confinement"] = (
            "server_sandbox"
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "contract.json"
            path.write_text(json.dumps(contract), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "confinement drifted"):
                host_control.load_contract(path)

    def test_server_exit_cannot_be_promoted_to_process_tree_barrier(self):
        contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
        contract["termination_boundary"]["server_exit_process_tree_barrier"] = (
            "qualified"
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "contract.json"
            path.write_text(json.dumps(contract), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "termination boundary drifted"):
                host_control.load_contract(path)


if __name__ == "__main__":
    unittest.main()
