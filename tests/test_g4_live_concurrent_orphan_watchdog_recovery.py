import hashlib
import json
from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]
RECORD = ROOT / "probes" / "g4-live-concurrent-orphan-watchdog-recovery-20260908.json"
SOURCE = ROOT / "probes" / "g4-live-concurrent-batch-orphan-negative-20260908.json"
SHA256 = re.compile(r"^[0-9a-f]{64}$")


class G4LiveConcurrentOrphanWatchdogRecoveryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.record = json.loads(RECORD.read_text(encoding="utf-8"))

    def test_recovery_binds_the_exact_source_negative_and_active_identity(self):
        source = self.record["source_negative"]
        active = self.record["exact_active_input"]
        self.assertEqual(source["sha256"], hashlib.sha256(SOURCE.read_bytes()).hexdigest())
        self.assertEqual(source["child_terminal_event"], "turn_aborted")
        self.assertFalse(source["subagent_stop_observed"])
        self.assertEqual(active["assignment_id"], "c81ce04d-9106-4306-b4e3-e4d36b7b4c00")
        self.assertEqual(active["assignment_mutation_mode"], "read_only")
        self.assertEqual(active["owned_paths"], [])
        self.assertTrue(active["only_active_bucket_present_before"])
        self.assertRegex(active["active_state_sha256"], SHA256)

    def test_watchdog_uses_one_exact_expired_selector_and_fail_closed_exit(self):
        watchdog = self.record["watchdog"]
        active = self.record["exact_active_input"]
        self.assertEqual(watchdog["selection"], "exact")
        self.assertEqual(watchdog["requested_assignment_ids"], [active["assignment_id"]])
        self.assertTrue(watchdog["fail_on_termination"])
        self.assertEqual(watchdog["exit_code"], 2)
        self.assertTrue(watchdog["valid"])
        self.assertEqual(watchdog["terminated_count"], 1)
        self.assertTrue(watchdog["parent_cancel_required"])
        for field in (
            "entry_point_sha256",
            "runtime_guard_sha256",
            "compatibility_state_sha256",
            "stdout_sha256",
            "stderr_sha256",
        ):
            self.assertRegex(watchdog[field], SHA256)

    def test_head_drift_is_incomparable_and_not_attributed(self):
        active = self.record["exact_active_input"]
        evidence = self.record["watchdog"]["termination_evidence"]
        self.assertEqual(evidence["reason"], "assignment_timeout")
        self.assertEqual(evidence["classification"], "initial_authority_mismatch")
        self.assertIsNone(evidence["disk_changed"])
        self.assertFalse(evidence["baseline_comparable"])
        self.assertIsNone(evidence["provenance_status"])
        self.assertNotEqual(evidence["snapshot"]["head"], active["base_head"])
        self.assertEqual(evidence["snapshot"]["git_status_short"], "")
        self.assertEqual(evidence["snapshot"]["changed_paths"], [])

    def test_expired_active_moves_only_to_unresolved(self):
        transition = self.record["state_transition"]
        self.assertEqual((transition["source"], transition["destination"]), ("active", "unresolved"))
        self.assertTrue(transition["active_absent_after"])
        self.assertTrue(transition["reported_absent_after"])
        self.assertTrue(transition["unresolved_present_after"])
        self.assertTrue(transition["consumed_absent_after"])
        self.assertTrue(transition["lost_absent_after"])
        self.assertFalse(transition["authority_deleted"])
        self.assertFalse(transition["terminal_success_inferred"])
        self.assertFalse(transition["contribution_attributed_to_child"])
        self.assertRegex(transition["unresolved_state_sha256"], SHA256)

    def test_process_absence_does_not_become_termination_or_quiescence_proof(self):
        barrier = self.record["post_watchdog_barrier"]
        self.assertEqual(barrier["candidate_process_match_count"], 0)
        self.assertEqual(barrier["git_status_short"], "")
        self.assertTrue(barrier["external_process_absence_observed"])
        self.assertFalse(barrier["host_termination_acknowledgement_observed"])
        self.assertFalse(barrier["mutations_quiesced_guarantee_observed"])
        self.assertFalse(barrier["quiescence_receipt_written"])
        self.assertFalse(barrier["strong_global_quiescence_claimed"])

    def test_partial_recovery_keeps_phase_and_handover_closed(self):
        verdict = self.record["scope_verdict"]
        self.assertTrue(verdict["live_exact_watchdog_selector_observed"])
        self.assertTrue(verdict["expired_active_frozen_fail_closed"])
        self.assertTrue(verdict["stale_active_bucket_cleared"])
        self.assertTrue(verdict["unresolved_evidence_preserved"])
        self.assertTrue(verdict["baseline_mismatch_left_unattributed"])
        self.assertTrue(verdict["p5a_watchdog_sample_advanced"])
        self.assertFalse(verdict["subagentstop_callback_gap_repaired"])
        self.assertFalse(verdict["host_termination_quiescence_qualified"])
        self.assertFalse(verdict["ownership_handover_authorized"])
        self.assertFalse(verdict["orphan_recovery_fully_qualified"])
        self.assertFalse(verdict["phase1_complete"])
        self.assertFalse(verdict["direct_write_qualified"])
        self.assertFalse(verdict["phase2_open"])
        self.assertFalse(verdict["phase3_open"])


if __name__ == "__main__":
    unittest.main()
