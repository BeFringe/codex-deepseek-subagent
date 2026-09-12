import json
from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]
RECORD = ROOT / "probes" / "g4-live-concurrent-batch-orphan-negative-20260908.json"
SHA256 = re.compile(r"^[0-9a-f]{64}$")


class G4LiveConcurrentBatchOrphanNegativeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.record = json.loads(RECORD.read_text(encoding="utf-8"))

    def test_runtime_is_isolated_current_read_only_candidate(self):
        runtime = self.record["runtime"]
        self.assertEqual(runtime["semantic_role"], "current_signed_runtime")
        self.assertEqual(runtime["parent_model_provider"], "openai")
        self.assertEqual(runtime["child_model_provider"], "openai")
        self.assertFalse(runtime["gui_app_server_selected"])
        self.assertFalse(runtime["credential_value_observed"])
        self.assertEqual(runtime["sandbox"], "read-only")
        self.assertEqual(runtime["approval_policy"], "never")

    def test_requested_concurrent_cohort_never_formed(self):
        live = self.record["live_probe"]
        first, second = live["requested_cohort"]
        self.assertEqual(live["parent"]["spawn_call_count"], 1)
        self.assertTrue(live["parent"]["declared_probe_failure"])
        self.assertTrue(first["spawn_call_observed"])
        self.assertFalse(second["spawn_call_observed"])
        self.assertEqual(first["requested_task_name"], "g4_concurrent_identity_a1")
        self.assertEqual(second["requested_task_name"], "g4_concurrent_identity_b1")
        scope = self.record["scope_boundary"]
        self.assertFalse(scope["same_assistant_batch_is_a_required_qualification_property"])
        self.assertFalse(scope["actual_child_execution_overlap_observed"])
        self.assertFalse(scope["two_child_concurrent_identity_cohort_formed"])

    def test_single_started_child_has_exact_real_identity_and_one_read_only_tool(self):
        child = self.record["live_probe"]["child_a"]
        parent = self.record["live_probe"]["parent"]
        self.assertEqual(child["parent_thread_id"], parent["thread_id"])
        self.assertEqual(child["runtime_session_id"], parent["runtime_session_id"])
        self.assertEqual(child["canonical_agent_path"], "/root/g4_concurrent_identity_a1")
        self.assertEqual(child["agent_type"], "g4_qualification_probe_worker")
        self.assertEqual(child["assignment_mutation_mode"], "read_only")
        self.assertEqual(child["owned_paths"], [])
        self.assertEqual(child["native_tool_name"], "list_agents")
        self.assertEqual(child["native_tool_call_count"], 1)
        self.assertTrue(child["native_tool_result_observed_parent_and_child_running"])
        for field in (
            "assignment_id",
            "handoff_id",
            "thread_id",
            "turn_id",
            "spawn_tool_use_id",
        ):
            self.assertTrue(child[field])
        for field in ("assignment_sha256", "capsule_sha256", "rollout_sha256"):
            self.assertRegex(child[field], SHA256)

    def test_parent_completion_interrupts_child_without_subagentstop(self):
        live = self.record["live_probe"]
        child = live["child_a"]
        chain = live["hook_event_chain"]
        self.assertEqual(child["turn_aborted_reason"], "interrupted")
        self.assertFalse(child["task_complete_observed"])
        self.assertFalse(child["assistant_final_attestation_observed"])
        self.assertEqual(child["subagent_stop_observation_count"], 0)
        self.assertEqual(live["headless_harness"]["child_abort_after_parent_task_complete_ms"], 16)
        self.assertEqual(
            [event["hook_event_name"] for event in chain["events"]],
            ["PreToolUse", "SubagentStart", "PreToolUse"],
        )
        self.assertEqual([event["sequence"] for event in chain["events"]], [1390, 1391, 1392])
        self.assertFalse(chain["subagent_stop_observed"])
        for event in chain["events"]:
            self.assertRegex(event["receipt_sha256"], SHA256)

    def test_process_barrier_does_not_conflate_stale_active_state_with_quiescence(self):
        barrier = self.record["live_probe"]["post_restart_barrier"]
        self.assertEqual(barrier["candidate_process_match_count"], 0)
        self.assertEqual(barrier["git_status_short"], "")
        self.assertTrue(barrier["process_absence_observed"])
        self.assertFalse(barrier["reported_state_present"])
        self.assertFalse(barrier["unresolved_state_present"])
        self.assertFalse(barrier["consumed_state_present"])
        self.assertFalse(barrier["lost_state_present"])
        self.assertFalse(barrier["active_state_artificially_reclassified"])
        self.assertFalse(barrier["hook_state_quiescence_observed"])
        self.assertFalse(barrier["strong_global_quiescence_claimed"])
        self.assertRegex(barrier["active_state_sha256"], SHA256)

    def test_negative_receipt_preserves_fail_closed_phase_verdict(self):
        scope = self.record["scope_boundary"]
        verdict = self.record["verdict"]
        self.assertTrue(scope["stale_active_authority_after_process_exit_observed"])
        self.assertFalse(scope["terminal_callback_continuity_observed"])
        self.assertFalse(scope["durable_terminal_state_observed"])
        self.assertFalse(scope["mutation_observed"])
        self.assertFalse(scope["disk_changed"])
        self.assertTrue(verdict["valid_negative_evidence"])
        self.assertTrue(verdict["p5b_termination_callback_gap_observed"])
        self.assertFalse(verdict["orphan_state_recovery_qualified"])
        self.assertFalse(verdict["concurrent_identity_qualified"])
        self.assertFalse(verdict["strong_global_quiescence_qualified"])
        self.assertFalse(verdict["direct_write_qualified"])
        self.assertFalse(verdict["phase1_complete"])
        self.assertFalse(verdict["phase2_open"])
        self.assertFalse(verdict["phase3_open"])


if __name__ == "__main__":
    unittest.main()
