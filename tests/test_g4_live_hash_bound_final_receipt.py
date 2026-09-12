import json
from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]
RECEIPT = ROOT / "probes" / "g4-live-hash-bound-final-receipt-20260909.json"
STATUS = ROOT / "probes" / "phase1-g4-status.json"
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class G4LiveHashBoundFinalReceiptTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.receipt = json.loads(RECEIPT.read_text(encoding="utf-8"))

    def test_runtime_and_identity_remain_native_and_exact(self):
        runtime = self.receipt["runtime"]
        identity = self.receipt["identity"]
        self.assertEqual(runtime["parent_model_provider"], "openai")
        self.assertEqual(runtime["child_model_provider"], "openai")
        self.assertFalse(runtime["gui_app_server_selected"])
        self.assertFalse(runtime["credential_value_observed"])
        self.assertEqual(runtime["exit_code"], 0)
        self.assertEqual(identity["parent_thread_id"], identity["runtime_session_id"])
        self.assertNotEqual(identity["child_thread_id"], identity["parent_thread_id"])
        self.assertEqual(identity["canonical_agent_path"], "/root/g4_final_receipt_4")
        self.assertEqual(identity["child_final_sha256"], identity["parent_callback_sha256"])
        self.assertTrue(identity["parent_child_final_exactly_equal"])

    def test_hash_bound_receipt_is_the_final_derivation_receipt(self):
        receipt = self.receipt["writer_receipt"]
        self.assertEqual(receipt["schema"], 2)
        self.assertTrue(SHA256_RE.fullmatch(receipt["receipt_sha256"]))
        self.assertEqual(
            receipt["receipt_sha256"],
            receipt["final_derivation_receipt_sha256"],
        )
        self.assertEqual(receipt["paths"], ["qualified.txt"])
        self.assertEqual(
            receipt["actor_thread_id"],
            self.receipt["identity"]["child_thread_id"],
        )
        self.assertEqual(
            receipt["actor_agent_path"],
            self.receipt["identity"]["canonical_agent_path"],
        )
        self.assertEqual(self.receipt["authority"]["final_rejection_count"], 0)
        self.assertEqual(self.receipt["authority"]["durable_state"], "reported")

    def test_child_posttooluse_is_visible_in_one_contiguous_hook_chain(self):
        chain = self.receipt["hook_chain"]
        sequences = chain["sequences"]
        self.assertEqual(
            list(sequences.values()),
            list(range(sequences["spawn_pretool"], sequences["subagent_stop"] + 1)),
        )
        self.assertEqual(chain["pretool_tool_use_id"], chain["posttool_tool_use_id"])
        self.assertFalse(chain["raw_payload_stored"])

    def test_fresh_owner_barrier_is_positive_but_not_global_quiescence(self):
        barrier = self.receipt["fresh_owner_disk_barrier"]
        self.assertEqual(
            barrier["target_sha256"],
            "4fd8e8f97e640e495fefed6d4fdb0467c4e5835d9bd006173da14af37698ac8c",
        )
        self.assertFalse(barrier["late_write_observed"])
        self.assertEqual(barrier["candidate_process_count"], 0)
        self.assertEqual(barrier["matching_writer_claim_count"], 0)
        self.assertFalse(barrier["strong_global_quiescence_claimed"])

    def test_scope_verdict_remains_fail_closed(self):
        verdict = self.receipt["verdict"]
        self.assertTrue(verdict["hash_bound_postmutation_final_receipt_subgate_qualified"])
        self.assertTrue(verdict["child_posttooluse_audit_visibility_qualified"])
        self.assertFalse(verdict["strong_global_quiescence_qualified"])
        self.assertFalse(verdict["all_mutation_surfaces_qualified"])
        self.assertFalse(verdict["phase1_complete"])
        self.assertFalse(verdict["direct_write_qualified"])
        self.assertEqual(verdict["phase2_state"], "closed")
        self.assertEqual(verdict["phase3_state"], "closed")

    def test_provider_free_checks_preserve_fail_closed_promotion(self):
        verification = self.receipt["provider_free_verification"]
        self.assertEqual(verification["discovered_test_count"], 675)
        self.assertEqual(verification["functional_pass_count"], 674)
        self.assertEqual(verification["prototype_location_artifact_count"], 1)
        self.assertTrue(verification["same_test_passes_in_real_repository"])
        for name in ("phase1", "mutation", "same_uid"):
            self.assertEqual(verification[f"{name}_gate_exit_code"], 0)
            self.assertEqual(verification[f"{name}_promotion_exit_code"], 2)
        self.assertFalse(verification["same_uid_rollout_protected"])
        self.assertFalse(verification["same_uid_state_protected"])

    def test_gates_reference_the_frozen_receipt_without_opening_phase1(self):
        status = json.loads(STATUS.read_text(encoding="utf-8"))
        gates = {gate["id"]: gate for gate in status["phase1"]["gates"]}
        receipt_path = "probes/g4-live-hash-bound-final-receipt-20260909.json"
        for gate_id in ("P1", "P2", "P3", "P4", "P5b", "P6", "P6a", "P6b", "P7"):
            self.assertIn(receipt_path, gates[gate_id]["evidence"])
        self.assertEqual(gates["P1"]["state"], "qualified")
        for gate_id in ("P2", "P3", "P5b", "P6", "P6a", "P6b"):
            self.assertEqual(gates[gate_id]["state"], "qualified")
        self.assertEqual(gates["P4"]["state"], "qualified")
        self.assertEqual(gates["P7"]["state"], "qualified")


if __name__ == "__main__":
    unittest.main()
