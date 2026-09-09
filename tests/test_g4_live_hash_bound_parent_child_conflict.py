from datetime import datetime
import hashlib
import json
from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]
RECEIPT = ROOT / "probes" / "g4-live-hash-bound-parent-child-conflict-20260909.json"
ADJUDICATION = (
    ROOT
    / "probes"
    / "g4-live-hash-bound-parent-child-conflict-parent-adjudication-20260909.json"
)
STATUS = ROOT / "probes" / "phase1-g4-status.json"
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class G4LiveHashBoundParentChildConflictTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.receipt = json.loads(RECEIPT.read_text(encoding="utf-8"))
        cls.adjudication = json.loads(ADJUDICATION.read_text(encoding="utf-8"))

    def test_runtime_identity_and_selection_are_exact(self):
        runtime = self.receipt["runtime"]
        identity = self.receipt["identity"]
        self.assertEqual(runtime["parent_model_provider"], "openai")
        self.assertEqual(runtime["child_model_provider"], "openai")
        self.assertFalse(runtime["gui_app_server_selected"])
        self.assertFalse(runtime["credential_value_observed"])
        self.assertEqual(runtime["candidate_exit_code"], 0)
        self.assertEqual(identity["parent_thread_id"], identity["runtime_session_id"])
        self.assertNotEqual(identity["child_thread_id"], identity["parent_thread_id"])
        self.assertEqual(identity["canonical_agent_path"], "/root/g4_parent_conflict_final_1")
        self.assertEqual(identity["requested_task_name"], "g4_parent_conflict_final_1")

    def test_final_runtime_catalog_is_closed_and_cannot_spawn(self):
        catalog = self.receipt["runtime_tool_catalog"]
        self.assertEqual(catalog["receipt_count"], 2)
        self.assertTrue(catalog["receipts_byte_identical"])
        self.assertRegex(catalog["canonical_receipt_sha256"], SHA256_RE)
        self.assertEqual(
            catalog["registered_tools"],
            ["apply_patch", "g4_assignment.list_agents", "view_image"],
        )
        self.assertEqual(catalog["code_mode_tool_names"], {})
        self.assertFalse(catalog["can_manage_children"])
        self.assertTrue(catalog["catalog_closed"])

    def test_parent_denial_occurs_inside_child_lease_and_hook_chain(self):
        chain = self.receipt["hook_chain"]
        sequences = chain["sequences"]
        self.assertEqual(
            list(sequences.values()),
            list(range(sequences["spawn_pretool"], sequences["subagent_stop"] + 1)),
        )
        self.assertEqual(
            chain["child_pretool_tool_use_id"],
            chain["child_posttool_tool_use_id"],
        )
        self.assertTrue(chain["parent_denial_before_child_posttool"])
        self.assertTrue(chain["parent_denial_before_child_release"])
        conflict = self.receipt["parent_conflict"]
        writer = self.receipt["writer_receipt"]
        self.assertEqual(conflict["failure_code"], "TASK.WRITER_LEASE_BLOCKED")
        self.assertTrue(conflict["pre_execution"])
        self.assertEqual(conflict["conflicting_kinds"], ["writer_claim", "active"])
        self.assertLess(
            datetime.fromisoformat(conflict["observed_at"]),
            datetime.fromisoformat(writer["released_at"]),
        )
        self.assertEqual(conflict["parent_retry_count"], 0)

    def test_hash_bound_receipt_drives_final_and_callback(self):
        writer = self.receipt["writer_receipt"]
        terminal = self.receipt["terminal_and_callback"]
        self.assertEqual(writer["schema"], 2)
        self.assertEqual(
            writer["receipt_sha256"],
            writer["final_derivation_receipt_sha256"],
        )
        self.assertEqual(writer["paths"], ["qualified.txt"])
        self.assertEqual(
            writer["actor_thread_id"], self.receipt["identity"]["child_thread_id"]
        )
        self.assertTrue(terminal["accepted_subagentstop_present"])
        self.assertTrue(terminal["child_task_complete_present"])
        self.assertTrue(terminal["parent_turn_completed"])
        self.assertEqual(
            terminal["child_final_sha256"], terminal["parent_callback_envelope_sha256"]
        )
        self.assertTrue(terminal["parent_child_final_exactly_equal"])
        self.assertEqual(terminal["final_rejection_count"], 0)
        self.assertFalse(terminal["context_lost"])
        self.assertFalse(terminal["authority_violation"])

    def test_fresh_disk_preserves_only_child_bytes_without_global_claim(self):
        disk = self.receipt["probe_root_final_disk"]
        self.assertEqual(disk["target_bytes"], 25)
        self.assertEqual(
            disk["target_sha256"],
            "4fd8e8f97e640e495fefed6d4fdb0467c4e5835d9bd006173da14af37698ac8c",
        )
        self.assertFalse(disk["parent_conflict_content_observed"])
        self.assertEqual(disk["candidate_process_exact_match_count"], 0)
        self.assertEqual(disk["candidate_open_file_count"], 0)
        self.assertFalse(disk["late_write_observed"])
        self.assertFalse(disk["strong_global_quiescence_claimed"])

    def test_fresh_owner_consumes_the_immutable_evidence(self):
        adjudication = self.adjudication
        self.assertEqual(
            adjudication["input"]["sha256"],
            hashlib.sha256(RECEIPT.read_bytes()).hexdigest(),
        )
        self.assertEqual(set(adjudication["fresh_owner"].values()), {"pass"})
        self.assertEqual(adjudication["state_transition"]["before"], "reported")
        self.assertEqual(adjudication["state_transition"]["after"], "consumed")
        self.assertFalse(adjudication["state_transition"]["reported_exists_after_adjudication"])
        self.assertFalse(adjudication["authority"]["global_direct_write_promoted"])

    def test_installed_hook_skew_is_repaired_but_not_called_rollback_qualification(self):
        repair = self.receipt["installed_hook_schema_reconciliation"]
        self.assertEqual(repair["hooks_json_sha256_before"], repair["hooks_json_sha256_after"])
        self.assertFalse(repair["v4_configuration_changed"])
        self.assertFalse(repair["gui_app_server_changed"])
        self.assertFalse(repair["localcat_changed"])
        self.assertEqual(repair["updated_source_count"], 6)
        self.assertEqual(repair["state_capsules_validated_after_refresh"], 43)
        self.assertEqual(repair["state_capsule_validation_failures_after_refresh"], 0)
        self.assertEqual(
            repair["quarantined_envelope_sha256_before_restore"],
            repair["reported_envelope_sha256_after_restore"],
        )
        self.assertFalse(repair["functional_reload_observed"])
        self.assertFalse(repair["install_rollback_qualified"])

    def test_status_references_both_receipts_and_stays_fail_closed(self):
        status = json.loads(STATUS.read_text(encoding="utf-8"))
        gates = {gate["id"]: gate for gate in status["phase1"]["gates"]}
        receipt = "probes/g4-live-hash-bound-parent-child-conflict-20260909.json"
        adjudication = (
            "probes/"
            "g4-live-hash-bound-parent-child-conflict-parent-adjudication-20260909.json"
        )
        for gate_id in ("P4", "P5b", "P6", "P6a", "P6b", "P7"):
            self.assertIn(receipt, gates[gate_id]["evidence"])
            self.assertIn(adjudication, gates[gate_id]["evidence"])
        self.assertFalse(status["phase1"]["declared_complete"])
        self.assertFalse(status["phase1"]["declared_direct_write_qualified"])
        verdict = self.receipt["verdict"]
        self.assertTrue(verdict["hash_bound_parent_child_same_path_conflict_subgate_qualified"])
        self.assertFalse(verdict["strong_global_quiescence_qualified"])
        self.assertFalse(verdict["all_mutation_surfaces_qualified"])
        self.assertFalse(verdict["phase1_complete"])
        self.assertFalse(verdict["direct_write_qualified"])
        self.assertEqual(verdict["phase2_state"], "closed")
        self.assertEqual(verdict["phase3_state"], "closed")


if __name__ == "__main__":
    unittest.main()
