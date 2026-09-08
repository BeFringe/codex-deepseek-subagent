import hashlib
import json
from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]
RECEIPT = ROOT / "probes" / "g4-live-compact-resume-20260908.json"
ADJUDICATION = ROOT / "probes" / "g4-live-compact-resume-parent-adjudication-20260908.json"
STATUS = ROOT / "probes" / "phase1-g4-status.json"
SHA256 = re.compile(r"^[0-9a-f]{64}$")


class G4LiveCompactResumeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.receipt = json.loads(RECEIPT.read_text(encoding="utf-8"))
        cls.adjudication = json.loads(ADJUDICATION.read_text(encoding="utf-8"))
        cls.status = json.loads(STATUS.read_text(encoding="utf-8"))

    def test_timing_negative_fails_closed_after_real_compaction(self):
        negative = self.receipt["timing_negative"]
        watchdog = negative["watchdog"]
        verdict = negative["verdict"]

        self.assertEqual(negative["native_list_agents_call_count"], 3)
        self.assertEqual(negative["durable_recovery_count"], 1)
        self.assertEqual(negative["child_final_seed_recovery_count"], 0)
        self.assertFalse(negative["postcompact_tool_call_observed"])
        self.assertFalse(negative["subagentstop_accepted"])
        self.assertEqual(watchdog["exit_code"], 2)
        self.assertEqual(watchdog["reason"], "assignment_timeout")
        self.assertEqual(watchdog["classification"], "unresponsive_no_disk_change")
        self.assertEqual(watchdog["state_before"], "active")
        self.assertEqual(watchdog["state_after"], "unresolved")
        self.assertFalse(watchdog["disk_changed"])
        self.assertTrue(verdict["compaction_observed"])
        self.assertFalse(verdict["postcompact_reattestation_observed"])
        self.assertTrue(verdict["fail_closed"])
        self.assertFalse(verdict["terminal_success_claimed"])

    def test_positive_binds_exact_sessionmeta_and_agentpath(self):
        positive = self.receipt["positive"]

        self.assertEqual(positive["runtime_session_id"], positive["parent_thread_id"])
        self.assertNotEqual(positive["child_thread_id"], positive["parent_thread_id"])
        self.assertEqual(positive["agent_type"], "g4_qualification_probe_worker")
        self.assertEqual(positive["requested_task_name"], "g4_compact_resume_2")
        self.assertEqual(positive["canonical_agent_path"], "/root/g4_compact_resume_2")
        self.assertEqual(positive["assignment_mutation_mode"], "read_only")
        self.assertEqual(positive["owned_paths"], [])
        self.assertFalse(any(positive["git_authority"].values()))
        for field in (
            "assignment_sha256",
            "capsule_sha256",
            "compact_invariant_sha256",
            "provenance_policy_sha256",
            "capture_snapshot_sha256",
        ):
            self.assertRegex(positive[field], SHA256)

    def test_precompact_is_followed_by_fourth_tool_and_incremented_final(self):
        positive = self.receipt["positive"]
        sequence = positive["hook_chain"]["sequences"]

        self.assertEqual(len(positive["native_list_agents_calls"]), 4)
        self.assertEqual(len(set(positive["native_list_agents_calls"])), 4)
        self.assertEqual(
            positive["postcompact_tool_call_id"], positive["native_list_agents_calls"][-1]
        )
        self.assertLess(sequence["precompact"], sequence["postcompact_list_agents_pretool"])
        self.assertEqual(sequence["subagentstop_accepted"], sequence["subagentstop_schema_denial"] + 1)
        self.assertEqual(positive["durable_recovery_count"], 1)
        self.assertEqual(positive["accepted_final_recovery_count"], 1)
        self.assertFalse(positive["context_lost"])
        self.assertEqual(
            positive["verification"],
            [{"command": "native four-step list_agents compact-resume probe", "exit_code": 0}],
        )

    def test_callback_disk_and_overlay_rollback_are_exact(self):
        positive = self.receipt["positive"]
        overlay = self.receipt["qualification_overlay"]
        barrier = positive["fresh_owner_disk_barrier"]

        self.assertTrue(positive["parent_callback_exactly_equals_accepted_final"])
        self.assertEqual(positive["candidate_exit_code"], 0)
        self.assertEqual(barrier["git_status_short"], "")
        self.assertFalse(barrier["index_changed"])
        self.assertEqual(barrier["candidate_process_count"], 0)
        self.assertFalse(barrier["late_write_observed"])
        self.assertFalse(barrier["strong_global_quiescence_claimed"])
        self.assertEqual(overlay["restored_hooks_sha256"], overlay["base_hooks_sha256"])
        self.assertTrue(overlay["v4_entries_preserved"])
        self.assertFalse(overlay["qualification_write_options_added"])
        self.assertFalse(overlay["installed_hook_files_overwritten"])

    def test_fresh_owner_consumes_only_the_exact_frozen_receipt(self):
        adjudication = self.adjudication

        self.assertEqual(
            adjudication["input"]["sha256"], hashlib.sha256(RECEIPT.read_bytes()).hexdigest()
        )
        self.assertEqual(set(adjudication["fresh_owner"].values()), {"pass"})
        self.assertEqual(adjudication["state_transition"]["before"], "reported")
        self.assertEqual(adjudication["state_transition"]["after"], "consumed")
        self.assertRegex(adjudication["state_transition"]["consumed_envelope_sha256"], SHA256)
        self.assertFalse(adjudication["authority"]["global_direct_write_promoted"])
        verification = adjudication["verification"]
        self.assertEqual(verification["provider_free_suite"]["test_count"], 578)
        self.assertEqual(verification["provider_free_suite"]["exit_code"], 0)
        self.assertEqual(verification["phase1_gate_normal_exit_code"], 0)
        self.assertEqual(verification["phase1_gate_require_complete_exit_code"], 2)
        self.assertEqual(verification["mutation_matrix_blocker_count"], 13)
        self.assertFalse(verification["same_uid_rollout_protected"])
        self.assertFalse(verification["same_uid_state_protected"])

    def test_scope_stays_fail_closed_and_status_cites_receipts(self):
        scope = self.receipt["scope"]
        gates = {gate["id"]: gate for gate in self.status["phase1"]["gates"]}
        receipt_path = "probes/g4-live-compact-resume-20260908.json"
        adjudication_path = "probes/g4-live-compact-resume-parent-adjudication-20260908.json"

        for gate_id in ("P1", "P2", "P3", "P5", "P5b", "P6", "P6a", "P6b", "P7"):
            self.assertIn(receipt_path, gates[gate_id]["evidence"])
            self.assertIn(adjudication_path, gates[gate_id]["evidence"])
        self.assertFalse(scope["process_restart_resume_qualified"])
        self.assertFalse(scope["postcompact_scope_expansion_negative_live_qualified"])
        self.assertFalse(scope["strong_global_quiescence_qualified"])
        self.assertFalse(scope["phase1_complete"])
        self.assertFalse(scope["direct_write_qualified"])
        self.assertFalse(self.status["phase1"]["declared_complete"])
        self.assertFalse(self.status["phase1"]["declared_direct_write_qualified"])


if __name__ == "__main__":
    unittest.main()
