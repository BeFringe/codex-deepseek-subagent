import hashlib
import json
from pathlib import Path
import unittest


REPO = Path(__file__).resolve().parents[1]
INPUT_PATH = REPO / "probes" / "g4-live-root-lifecycle-adjudication-input-20260817.json"
RESULT_PATH = REPO / "probes" / "g4-live-root-lifecycle-adjudication-result-20260817.json"
STATUS_PATH = REPO / "probes" / "phase1-g4-status.json"


class G4LiveRootLifecycleAdjudicationTests(unittest.TestCase):
    def setUp(self):
        self.input = json.loads(INPUT_PATH.read_text(encoding="utf-8"))
        self.result = json.loads(RESULT_PATH.read_text(encoding="utf-8"))

    def test_result_hash_binds_the_exact_parent_adjudication_input(self):
        digest = hashlib.sha256(INPUT_PATH.read_bytes()).hexdigest()

        self.assertEqual(self.result["input_evidence"]["sha256"], digest)
        self.assertEqual(
            self.result["assignment_id"], self.input["identity"]["assignment_id"]
        )
        self.assertEqual(self.result["transition"]["source"], "reported")
        self.assertEqual(self.result["transition"]["destination"], "consumed")
        self.assertTrue(self.result["transition"]["reported_absent_after"])
        self.assertTrue(self.result["transition"]["active_absent_after"])
        self.assertTrue(
            all(value == "pass" for value in self.result["parent_adjudication"].values())
        )

    def test_live_chain_is_exact_but_does_not_promote_phase_or_direct_write(self):
        chain = self.input["live_chain"]
        verdict = self.result["scope_verdict"]

        self.assertEqual((chain["sequence_start"], chain["sequence_end"]), (606, 611))
        self.assertEqual(chain["child_tool_name"], "g4_assignmentlist_agents")
        self.assertEqual(chain["child_function_output_status"], "success")
        self.assertEqual(chain["stop_attempts"], 3)
        self.assertTrue(self.input["fresh_parent_observation"]["post_termination_root_clean"])
        self.assertFalse(self.input["runtime"]["gui_app_server_selected"])
        self.assertFalse(self.input["runtime"]["credential_values_observed_or_recorded"])
        self.assertTrue(verdict["root_read_only_assignment_consumed"])
        self.assertFalse(verdict["identity_cohort_complete"])
        self.assertFalse(verdict["phase1_complete"])
        self.assertFalse(verdict["direct_write_qualified"])

    def test_phase_gate_references_receipts_without_opening_future_authority(self):
        status = json.loads(STATUS_PATH.read_text(encoding="utf-8"))
        gates = {item["id"]: item for item in status["phase1"]["gates"]}
        result_path = "probes/g4-live-root-lifecycle-adjudication-result-20260817.json"

        self.assertIn(result_path, gates["P1"]["evidence"])
        self.assertEqual(gates["P1"]["state"], "qualified")
        for gate_id in ("P2", "P3", "P4", "P5b", "P6", "P6a", "P6b"):
            self.assertIn(result_path, gates[gate_id]["evidence"])
        for gate_id in ("P2", "P3", "P5b", "P6", "P6a"):
            self.assertEqual(gates[gate_id]["state"], "qualified")
        for gate_id in ("P4", "P6b"):
            self.assertEqual(gates[gate_id]["state"], "partial")
        self.assertFalse(status["phase1"]["declared_complete"])
        self.assertFalse(status["phase1"]["declared_direct_write_qualified"])
        self.assertEqual(status["phase2"]["state"], "closed")
        self.assertEqual(status["phase3"]["state"], "closed")


if __name__ == "__main__":
    unittest.main()
