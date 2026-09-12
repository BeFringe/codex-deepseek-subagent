import json
from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]
RECORD = ROOT / "probes" / "g4-live-concurrent-identity-20260908.json"
SHA256 = re.compile(r"^[0-9a-f]{64}$")


class G4LiveConcurrentIdentityTests(unittest.TestCase):
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

    def test_real_sessionmeta_binds_two_distinct_children_to_one_parent(self):
        live = self.record["live_probe"]
        parent = live["parent"]
        first, second = live["children"]
        self.assertEqual(parent["agent_path"], "/root")
        for child in (first, second):
            self.assertEqual(child["parent_thread_id"], parent["thread_id"])
            self.assertEqual(child["runtime_session_id"], parent["runtime_session_id"])
            self.assertEqual(child["agent_type"], "g4_qualification_probe_worker")
            self.assertEqual(child["assignment_mutation_mode"], "read_only")
            self.assertEqual(child["owned_paths"], [])
            self.assertEqual(child["excluded_paths"], [])
        for field in (
            "requested_task_name",
            "canonical_agent_path",
            "thread_id",
            "assignment_id",
            "handoff_id",
            "assignment_sha256",
            "capsule_sha256",
            "compact_invariant_sha256",
            "spawn_tool_use_id",
        ):
            self.assertNotEqual(first[field], second[field])

    def test_each_child_calls_one_identity_tool_and_reports_clean_base(self):
        for child in self.record["live_probe"]["children"]:
            self.assertEqual(child["native_tool_name"], "list_agents")
            self.assertEqual(child["native_tool_call_count"], 1)
            self.assertFalse(child["context_lost"])
            self.assertFalse(child["authority_violation"])
            self.assertTrue(child["assigned_slice_complete"])
            for field in (
                "assignment_sha256",
                "capsule_sha256",
                "compact_invariant_sha256",
                "capture_snapshot_sha256",
                "rollout_sha256",
                "reported_state_sha256",
                "final_attestation_canonical_json_sha256",
            ):
                self.assertRegex(child[field], SHA256)

    def test_real_overlap_is_witnessed_after_a_nonterminal_stop_attempt(self):
        live = self.record["live_probe"]
        order = live["concurrent_order"]
        first, second = live["children"]
        self.assertTrue(order["first_stop_attempt_was_not_terminal_completion"])
        self.assertTrue(order["child_b_start_before_child_a_accepted_stop"])
        self.assertTrue(order["child_b_list_observed_both_children_running"])
        self.assertTrue(order["actual_child_execution_overlap_observed"])
        self.assertGreater(order["observed_overlap_until_child_a_accepted_stop_ms"], 0)
        self.assertGreater(order["observed_overlap_until_child_a_task_complete_ms"], 0)
        self.assertEqual(
            second["list_result_agent_paths"],
            ["/root", first["canonical_agent_path"], second["canonical_agent_path"]],
        )

    def test_hook_chain_has_two_spawn_start_tool_and_final_stop_paths(self):
        chain = self.record["live_probe"]["hook_event_chain"]
        self.assertEqual(chain["event_count"], 11)
        self.assertEqual(chain["sequence_end"] - chain["sequence_start"] + 1, 11)
        self.assertEqual(
            chain["event_names"],
            [
                "PreToolUse",
                "SubagentStart",
                "PreToolUse",
                "SubagentStop",
                "PreToolUse",
                "SubagentStart",
                "PreToolUse",
                "SubagentStop",
                "SubagentStop",
                "SubagentStop",
                "SubagentStop",
            ],
        )
        self.assertEqual(len(chain["receipt_sha256_values"]), 11)
        for value in chain["receipt_sha256_values"]:
            self.assertRegex(value, SHA256)

    def test_parent_projection_gap_remains_fail_closed(self):
        live = self.record["live_probe"]
        parent = live["parent"]
        projection = live["parent_projection"]
        self.assertEqual(parent["spawn_call_count"], 2)
        self.assertEqual(parent["wait_call_count"], 2)
        self.assertEqual(parent["wait_timeout_count"], 0)
        self.assertFalse(parent["non_spawn_call_between_spawns"])
        self.assertTrue(parent["declared_probe_failure"])
        self.assertFalse(projection["spawn_results_exposed_child_thread_ids"])
        self.assertFalse(projection["wait_results_exposed_child_thread_ids"])
        self.assertFalse(projection["parent_could_self_adjudicate_exact_identity"])
        self.assertTrue(projection["fresh_owner_sessionmeta_hook_join_succeeded"])
        self.assertTrue(projection["projection_gap_is_not_reclassified_as_runtime_identity_failure"])

    def test_positive_sample_does_not_overclaim_cohort_or_phase_qualification(self):
        scope = self.record["scope_boundary"]
        verdict = self.record["verdict"]
        barrier = self.record["live_probe"]["post_termination_barrier"]
        self.assertTrue(scope["single_live_concurrent_positive_sample"])
        self.assertTrue(scope["actual_child_execution_overlap_observed"])
        self.assertTrue(scope["both_records_reported"])
        self.assertFalse(scope["both_records_fresh_owner_consumed"])
        self.assertFalse(scope["parent_projection_complete"])
        self.assertFalse(scope["concurrent_identity_cohort_qualified"])
        self.assertFalse(scope["mutation_authority_granted"])
        self.assertFalse(scope["strong_global_quiescence_qualified"])
        self.assertEqual(barrier["candidate_process_match_count"], 0)
        self.assertEqual(barrier["git_status_short"], "")
        self.assertFalse(barrier["strong_global_quiescence_claimed"])
        self.assertTrue(verdict["concurrent_identity_positive_sample"])
        self.assertTrue(verdict["parent_native_projection_gap_observed"])
        self.assertFalse(verdict["fresh_owner_integration_adjudication_complete"])
        self.assertFalse(verdict["direct_write_qualified"])
        self.assertFalse(verdict["phase1_complete"])
        self.assertFalse(verdict["phase2_open"])
        self.assertFalse(verdict["phase3_open"])


if __name__ == "__main__":
    unittest.main()
