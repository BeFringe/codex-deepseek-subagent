import copy
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "probes" / "check_phase1_g4.py"
STATUS = REPO / "probes" / "phase1-g4-status.json"

SPEC = importlib.util.spec_from_file_location("check_phase1_g4", SCRIPT)
check_phase1_g4 = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(check_phase1_g4)


class Phase1G4GateTests(unittest.TestCase):
    def write_status(self, value, directory):
        path = Path(directory) / "phase1-g4-status.json"
        path.write_text(json.dumps(value), encoding="utf-8")
        return path

    def test_current_status_keeps_all_future_authority_closed(self):
        result = check_phase1_g4.qualification(STATUS)

        self.assertTrue(result["valid"])
        self.assertFalse(result["phase1_complete"])
        self.assertFalse(result["direct_write_qualified"])
        self.assertEqual(result["phase2"], "closed")
        self.assertEqual(result["phase3"], "closed")
        self.assertTrue(result["gate_blockers"])
        self.assertTrue(result["exit_receipt_blockers"])

    def test_finite_identity_lifecycle_final_provenance_and_cost_gates_are_closed(self):
        value = json.loads(STATUS.read_text(encoding="utf-8"))
        gates = {gate["id"]: gate for gate in value["phase1"]["gates"]}

        self.assertEqual(gates["P2"]["state"], "qualified")
        self.assertEqual(gates["P2"]["provider_free"], "pass")
        self.assertNotIn("blocker", gates["P2"])
        self.assertEqual(gates["P3"]["state"], "qualified")
        self.assertEqual(gates["P3"]["provider_free"], "pass")
        self.assertNotIn("blocker", gates["P3"])
        self.assertEqual(gates["P6"]["state"], "qualified")
        self.assertEqual(gates["P6"]["provider_free"], "pass")
        self.assertNotIn("blocker", gates["P6"])
        self.assertEqual(gates["P6a"]["state"], "qualified")
        self.assertEqual(gates["P6a"]["provider_free"], "pass")
        self.assertNotIn("blocker", gates["P6a"])
        self.assertEqual(gates["P6b"]["state"], "qualified")
        self.assertEqual(gates["P6b"]["provider_free"], "pass")
        self.assertNotIn("blocker", gates["P6b"])
        self.assertEqual(gates["P6c"]["state"], "qualified")
        self.assertEqual(gates["P6c"]["provider_free"], "pass")
        self.assertNotIn("blocker", gates["P6c"])
        receipts = {
            receipt["id"]: receipt for receipt in value["phase1"]["exit_receipts"]
        }
        self.assertEqual(receipts["sessionmeta_identity"]["state"], "qualified")

    def test_require_complete_fails_closed(self):
        completed = subprocess.run(
            [sys.executable, str(SCRIPT), "--require-phase1-complete"],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )

        self.assertEqual(completed.returncode, 2, completed.stderr)
        result = json.loads(completed.stdout)
        self.assertTrue(result["valid"])
        self.assertFalse(result["phase1_complete"])

    def test_missing_subgate_is_invalid(self):
        value = json.loads(STATUS.read_text(encoding="utf-8"))
        value["phase1"]["gates"] = [
            gate for gate in value["phase1"]["gates"] if gate["id"] != "P6c"
        ]

        with tempfile.TemporaryDirectory() as directory:
            path = self.write_status(value, directory)
            with self.assertRaisesRegex(ValueError, "Phase 1 gates mismatch"):
                check_phase1_g4.load_status(path)

    def test_documentation_cannot_open_phase_two_early(self):
        value = json.loads(STATUS.read_text(encoding="utf-8"))
        value["phase2"]["state"] = "open"

        with tempfile.TemporaryDirectory(dir=REPO / "probes") as directory:
            path = self.write_status(value, directory)
            with self.assertRaisesRegex(ValueError, "Phase 2 must remain closed"):
                check_phase1_g4.load_status(path)

    def test_declared_boolean_cannot_override_blockers(self):
        value = copy.deepcopy(json.loads(STATUS.read_text(encoding="utf-8")))
        value["phase1"]["declared_complete"] = True
        value["phase1"]["declared_direct_write_qualified"] = True

        with tempfile.TemporaryDirectory(dir=REPO / "probes") as directory:
            path = self.write_status(value, directory)
            with self.assertRaisesRegex(ValueError, "declared Phase 1 completion"):
                check_phase1_g4.load_status(path)

    def test_app_server_host_control_cannot_replace_native_lifecycle(self):
        value = json.loads(STATUS.read_text(encoding="utf-8"))
        value["goal_contract"]["app_server_source_adjustment"][
            "may_substitute_native_child_lifecycle"
        ] = True

        with tempfile.TemporaryDirectory(dir=REPO / "probes") as directory:
            path = self.write_status(value, directory)
            with self.assertRaisesRegex(ValueError, "goal contract drifted"):
                check_phase1_g4.load_status(path)

    def test_app_server_bootstrap_denial_cannot_be_dropped(self):
        value = json.loads(STATUS.read_text(encoding="utf-8"))
        proofs = value["goal_contract"]["app_server_source_adjustment"][
            "required_proofs"
        ]
        proofs.remove("external_worker_bootstrap_denial_or_os_confinement")

        with tempfile.TemporaryDirectory(dir=REPO / "probes") as directory:
            path = self.write_status(value, directory)
            with self.assertRaisesRegex(ValueError, "goal contract drifted"):
                check_phase1_g4.load_status(path)

    def test_role_sandbox_declaration_cannot_replace_trusted_host_receipt(self):
        value = json.loads(STATUS.read_text(encoding="utf-8"))
        proofs = value["goal_contract"]["app_server_source_adjustment"][
            "required_proofs"
        ]
        proofs.remove("trusted_parent_or_host_sandbox_receipt")

        with tempfile.TemporaryDirectory(dir=REPO / "probes") as directory:
            path = self.write_status(value, directory)
            with self.assertRaisesRegex(ValueError, "goal contract drifted"):
                check_phase1_g4.load_status(path)


if __name__ == "__main__":
    unittest.main()
