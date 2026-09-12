import json
import hashlib
from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]
RECEIPT = ROOT / "probes" / "g4-live-exact-path-child-write-20260908.json"
ADJUDICATION = ROOT / "probes" / "g4-live-exact-path-child-write-parent-adjudication-20260908.json"
STATUS = ROOT / "probes" / "phase1-g4-status.json"
SHA = re.compile(r"^[0-9a-f]{64}$")


class G4LiveExactPathChildWriteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.receipt = json.loads(RECEIPT.read_text(encoding="utf-8"))
        cls.adjudication = json.loads(ADJUDICATION.read_text(encoding="utf-8"))
        cls.status = json.loads(STATUS.read_text(encoding="utf-8"))

    def test_real_sessionmeta_and_callback_identity_are_exact(self):
        identity = self.receipt["identity"]
        self.assertEqual(identity["runtime_session_id"], identity["parent_thread_id"])
        self.assertNotEqual(identity["child_thread_id"], identity["parent_thread_id"])
        self.assertEqual(identity["agent_type"], "g4_qualification_probe_worker")
        self.assertEqual(identity["canonical_agent_path"], "/root/g4_exact_write_1")
        self.assertTrue(identity["parent_child_final_exactly_equal"])
        for field in ("parent_rollout_sha256", "child_rollout_sha256", "final_message_sha256"):
            self.assertRegex(identity[field], SHA)

    def test_ceiling_is_host_derived_exact_and_non_git(self):
        authority = self.receipt["authority"]
        consent = authority["trusted_host_user_write_consent"]
        self.assertEqual(authority["assignment_mutation_mode"], "write")
        self.assertEqual(authority["parent_recorded_user_write_intent"], "allow")
        self.assertEqual(consent["status"], "verified")
        self.assertEqual(consent["source"], "qualification_hook_exact_path")
        self.assertRegex(consent["receipt_sha256"], SHA)
        self.assertEqual(authority["owned_paths"], ["qualified.txt"])
        self.assertFalse(any(authority["git_authority"].values()))
        self.assertFalse(authority["context_lost"])

    def test_writer_lease_joins_same_child_tool_and_disk(self):
        identity = self.receipt["identity"]
        lease = self.receipt["writer_lease"]
        barrier = self.receipt["fresh_owner_disk_barrier"]
        self.assertEqual(lease["actor_thread_id"], identity["child_thread_id"])
        self.assertEqual(lease["actor_agent_path"], identity["canonical_agent_path"])
        self.assertEqual(lease["tool_name"], "apply_patch")
        self.assertEqual(lease["paths"], ["qualified.txt"])
        self.assertTrue(lease["posttooluse_released"])
        self.assertEqual(lease["matching_claims_after_release"], 0)
        self.assertEqual(barrier["target_sha256"], "4fd8e8f97e640e495fefed6d4fdb0467c4e5835d9bd006173da14af37698ac8c")
        self.assertEqual(barrier["git_status_short"], "?? qualified.txt")
        self.assertEqual(barrier["candidate_process_count"], 0)
        self.assertFalse(barrier["late_write_observed"])
        self.assertFalse(barrier["strong_global_quiescence_claimed"])

    def test_hook_overlay_rolled_back_and_v4_was_preserved(self):
        overlay = self.receipt["qualification_overlay"]
        self.assertNotEqual(overlay["overlay_hooks_sha256"], overlay["base_hooks_sha256"])
        self.assertEqual(overlay["restored_hooks_sha256"], overlay["base_hooks_sha256"])
        self.assertTrue(overlay["v4_entries_preserved"])
        self.assertFalse(overlay["installed_hook_files_overwritten"])

    def test_verdict_advances_one_surface_without_global_promotion(self):
        verdict = self.receipt["verdict"]
        self.assertTrue(verdict["one_live_positive_child_write_qualified"])
        self.assertFalse(verdict["all_mutation_surfaces_qualified"])
        self.assertFalse(verdict["strong_termination_quiescence_qualified"])
        self.assertFalse(verdict["phase1_complete"])
        self.assertFalse(verdict["direct_write_qualified"])
        self.assertEqual(verdict["phase2_state"], "closed")
        self.assertEqual(verdict["phase3_state"], "closed")

    def test_fresh_owner_consumes_exact_frozen_evidence(self):
        adjudication = self.adjudication
        self.assertEqual(
            adjudication["input"]["sha256"],
            hashlib.sha256(RECEIPT.read_bytes()).hexdigest(),
        )
        self.assertEqual(set(adjudication["fresh_owner"].values()), {"pass"})
        self.assertEqual(adjudication["state_transition"]["before"], "reported")
        self.assertEqual(adjudication["state_transition"]["after"], "consumed")
        self.assertFalse(adjudication["authority"]["global_direct_write_promoted"])

    def test_global_status_remains_fail_closed(self):
        gates = {gate["id"]: gate for gate in self.status["phase1"]["gates"]}
        evidence = "probes/g4-live-exact-path-child-write-20260908.json"
        adjudication = "probes/g4-live-exact-path-child-write-parent-adjudication-20260908.json"
        for gate_id in ("P1", "P2", "P3", "P4", "P5b", "P6", "P6a", "P6b", "P7"):
            self.assertIn(evidence, gates[gate_id]["evidence"])
            self.assertIn(adjudication, gates[gate_id]["evidence"])
        self.assertFalse(self.status["phase1"]["declared_complete"])
        self.assertFalse(self.status["phase1"]["declared_direct_write_qualified"])


if __name__ == "__main__":
    unittest.main()
