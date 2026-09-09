from datetime import datetime
import json
from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]
RECEIPT = ROOT / "probes" / "g4-live-parent-child-same-path-conflict-20260909.json"
STATUS = ROOT / "probes" / "phase1-g4-status.json"
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class G4LiveParentChildSamePathConflictTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.receipt = json.loads(RECEIPT.read_text(encoding="utf-8"))

    def test_runtime_identity_is_exact_and_provider_local(self):
        runtime = self.receipt["runtime"]
        identity = self.receipt["identity"]
        self.assertEqual(runtime["parent_model_provider"], "openai")
        self.assertEqual(runtime["child_model_provider"], "openai")
        self.assertFalse(runtime["gui_app_server_selected"])
        self.assertFalse(runtime["credential_value_observed"])
        self.assertEqual(identity["parent_thread_id"], identity["runtime_session_id"])
        self.assertNotEqual(identity["child_thread_id"], identity["parent_thread_id"])
        self.assertEqual(identity["canonical_agent_path"], "/root/g4_parent_conflict_5")
        self.assertEqual(identity["agent_type"], "g4_qualification_probe_worker")

    def test_overlay_is_reproducible_and_fully_rolled_back(self):
        overlay = self.receipt["qualification_overlay"]
        self.assertNotEqual(overlay["overlay_hooks_sha256"], overlay["base_hooks_sha256"])
        self.assertEqual(overlay["restored_hooks_sha256"], overlay["base_hooks_sha256"])
        self.assertTrue(overlay["v4_entries_preserved"])
        self.assertFalse(overlay["installed_hook_files_overwritten"])
        self.assertTrue(SHA256_RE.fullmatch(overlay["wrapper_sha256"]))

    def test_parent_denial_occurs_while_child_claim_is_inflight(self):
        timeline = self.receipt["lease_timeline"]
        child_pretool = timeline["child_pretool"]
        denial = timeline["parent_denial"]
        release = timeline["child_release"]
        self.assertLess(child_pretool["sequence"], denial["sequence"])
        self.assertLess(
            datetime.fromisoformat(denial["observed_at"]),
            datetime.fromisoformat(release["released_at"]),
        )
        self.assertEqual(child_pretool["claim_id"], "d0b31b82-34c1-424d-a490-285461b15a00")
        self.assertEqual(denial["event_stage"], "denied")
        self.assertEqual(denial["failure_code"], "TASK.WRITER_LEASE_BLOCKED")
        self.assertTrue(denial["pre_execution"])
        self.assertEqual(denial["conflicting_kinds"], ["writer_claim", "active"])

    def test_parent_bytes_do_not_replace_child_bytes(self):
        root = self.receipt["probe_root"]
        barrier = self.receipt["fresh_owner_disk_barrier"]
        self.assertEqual(root["owned_paths"], ["qualified.txt"])
        self.assertEqual(root["target_bytes"], 25)
        self.assertEqual(
            root["target_sha256"],
            "4fd8e8f97e640e495fefed6d4fdb0467c4e5835d9bd006173da14af37698ac8c",
        )
        self.assertFalse(root["parent_conflict_content_observed"])
        self.assertEqual(barrier["target_sha256"], root["target_sha256"])
        self.assertFalse(barrier["late_write_observed"])

    def test_incomplete_terminal_chain_is_not_promoted(self):
        terminal = self.receipt["termination_and_state"]
        self.assertGreater(len(terminal["subagentstop_sequences"]), 1)
        self.assertFalse(terminal["accepted_subagentstop_present"])
        self.assertFalse(terminal["parent_callback_present"])
        self.assertFalse(terminal["parent_turn_completed"])
        self.assertFalse(terminal["candidate_exit_code_observed"])
        self.assertFalse(terminal["durable_resolution_qualified"])
        self.assertEqual(terminal["current_assignment_state"], "quarantined_active_envelope")

    def test_fresh_owner_barrier_is_narrow_not_global_quiescence(self):
        barrier = self.receipt["fresh_owner_disk_barrier"]
        for field in (
            "matching_writer_claim_count",
            "matching_live_assignment_state_count",
            "candidate_process_exact_match_count",
            "candidate_open_file_count",
        ):
            self.assertEqual(barrier[field], 0)
        self.assertFalse(barrier["strong_global_quiescence_claimed"])

    def test_verdict_advances_only_parent_apply_patch_surface(self):
        verdict = self.receipt["verdict"]
        self.assertTrue(verdict["parent_same_path_apply_patch_preexecution_mediation_qualified"])
        self.assertTrue(verdict["inflight_child_lease_ordering_qualified"])
        self.assertFalse(verdict["child_posttooluse_audit_visibility_qualified_for_this_run"])
        self.assertFalse(verdict["callback_continuity_qualified_for_this_run"])
        self.assertFalse(verdict["termination_quiescence_qualified_for_this_run"])
        self.assertFalse(verdict["all_mutation_surfaces_qualified"])
        self.assertFalse(verdict["phase1_complete"])
        self.assertFalse(verdict["direct_write_qualified"])
        self.assertEqual(verdict["phase2_state"], "closed")
        self.assertEqual(verdict["phase3_state"], "closed")

    def test_partial_status_references_the_receipt(self):
        status = json.loads(STATUS.read_text(encoding="utf-8"))
        gates = {gate["id"]: gate for gate in status["phase1"]["gates"]}
        evidence = "probes/g4-live-parent-child-same-path-conflict-20260909.json"
        for gate_id in ("P4", "P5b"):
            self.assertIn(evidence, gates[gate_id]["evidence"])
            self.assertEqual(gates[gate_id]["state"], "partial")
        self.assertFalse(status["phase1"]["declared_complete"])
        self.assertFalse(status["phase1"]["declared_direct_write_qualified"])


if __name__ == "__main__":
    unittest.main()
