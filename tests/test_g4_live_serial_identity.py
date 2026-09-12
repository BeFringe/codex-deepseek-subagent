import json
from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]
RECORD = ROOT / "probes" / "g4-live-serial-identity-20260908.json"
SHA256 = re.compile(r"^[0-9a-f]{64}$")


class G4LiveSerialIdentityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.record = json.loads(RECORD.read_text(encoding="utf-8"))

    def test_runtime_is_current_isolated_read_only_candidate(self):
        runtime = self.record["runtime"]
        self.assertEqual(runtime["semantic_role"], "current_signed_runtime")
        self.assertEqual(runtime["parent_model_provider"], "openai")
        self.assertEqual(runtime["child_model_provider"], "openai")
        self.assertFalse(runtime["gui_app_server_selected"])
        self.assertFalse(runtime["credential_value_observed"])
        self.assertEqual(runtime["sandbox"], "read-only")
        self.assertEqual(runtime["approval_policy"], "never")

    def test_real_sessionmeta_binds_two_distinct_children_to_one_parent(self):
        probe = self.record["live_probe"]
        parent = probe["parent"]
        first, second = probe["children"]
        self.assertEqual(parent["agent_path"], "/root")
        for child in (first, second):
            self.assertEqual(child["parent_thread_id"], parent["thread_id"])
            self.assertEqual(child["runtime_session_id"], parent["runtime_session_id"])
            self.assertEqual(child["agent_type"], "g4_qualification_probe_worker")
        for field in (
            "thread_id",
            "turn_id",
            "requested_task_name",
            "canonical_agent_path",
            "assignment_id",
            "handoff_id",
            "assignment_sha256",
            "capsule_sha256",
            "compact_invariant_sha256",
            "spawn_tool_use_id",
        ):
            self.assertNotEqual(first[field], second[field])
        self.assertEqual(first["canonical_agent_path"], "/root/g4_serial_identity_a1")
        self.assertEqual(second["canonical_agent_path"], "/root/g4_serial_identity_b1")

    def test_each_child_called_only_the_read_only_identity_tool(self):
        for child in self.record["live_probe"]["children"]:
            self.assertEqual(child["assignment_mutation_mode"], "read_only")
            self.assertEqual(child["trusted_host_user_write_consent_status"], "unavailable")
            self.assertEqual(child["native_tool_name"], "list_agents")
            self.assertEqual(child["native_tool_call_count"], 1)
            final = child["final_attestation"]
            self.assertEqual(final["verification_exit_code"], 0)
            self.assertEqual(final["git_status_short"], "")
            self.assertEqual(final["changed_paths"], [])
            self.assertFalse(final["context_lost"])
            self.assertFalse(final["authority_violation"])
            self.assertTrue(final["assigned_slice_complete"])

    def test_hook_chain_preserves_exact_serial_order(self):
        chain = self.record["live_probe"]["hook_event_chain"]
        events = chain["events"]
        self.assertEqual(chain["event_count"], 9)
        self.assertEqual([event["sequence"] for event in events], list(range(1341, 1350)))
        self.assertEqual(
            [event["hook_event_name"] for event in events],
            [
                "PreToolUse",
                "SubagentStart",
                "PreToolUse",
                "SubagentStop",
                "SubagentStop",
                "PreToolUse",
                "SubagentStart",
                "PreToolUse",
                "SubagentStop",
            ],
        )
        for event in events:
            self.assertTrue(SHA256.fullmatch(event["receipt_sha256"]))
        order = self.record["live_probe"]["serial_order"]
        self.assertTrue(order["child_b_spawn_after_child_a_parent_callback"])
        self.assertGreater(order["callback_to_next_spawn_gap_ms"], 0)
        self.assertFalse(order["overlapping_child_execution_observed"])
        self.assertFalse(order["first_wait_timed_out"])
        self.assertFalse(order["second_wait_timed_out"])

    def test_subagentstop_rejects_wrong_shape_then_accepts_correction(self):
        first, second = self.record["live_probe"]["children"]
        self.assertEqual(first["subagent_stop_observation_count"], 2)
        self.assertEqual(first["correction_prompt_count"], 1)
        self.assertEqual(
            first["first_stop_result"], "TASK.FINAL_INVALID_FINAL_WITHOUT_CONTRIBUTION"
        )
        self.assertEqual(second["subagent_stop_observation_count"], 1)
        self.assertEqual(second["correction_prompt_count"], 0)

    def test_durable_records_are_reported_but_not_owner_consumed(self):
        scope = self.record["scope_boundary"]
        self.assertTrue(scope["both_records_reported"])
        self.assertFalse(scope["both_records_fresh_owner_consumed"])
        for child in self.record["live_probe"]["children"]:
            for field in (
                "rollout_sha256",
                "reported_state_sha256",
                "final_attestation_canonical_json_sha256",
            ):
                self.assertTrue(SHA256.fullmatch(child[field]))

    def test_harness_error_does_not_invent_candidate_exit_code(self):
        harness = self.record["live_probe"]["headless_harness"]
        self.assertTrue(harness["parent_task_complete_observed"])
        self.assertFalse(harness["candidate_exit_code_observed"])
        self.assertEqual(harness["outer_shell_exit_code"], 1)
        self.assertIn("read-only variable", harness["outer_shell_recording_error"])
        self.assertFalse(harness["retry_performed"])

    def test_post_termination_barrier_is_clean_but_not_global_quiescence(self):
        barrier = self.record["live_probe"]["post_termination_barrier"]
        repository = self.record["repository"]
        self.assertEqual(barrier["candidate_process_match_count"], 0)
        self.assertEqual(barrier["head"], repository["source_commit"])
        self.assertEqual(barrier["head_tree"], repository["source_tree"])
        self.assertEqual(barrier["git_status_short"], "")
        self.assertFalse(barrier["strong_global_quiescence_claimed"])

    def test_scope_advances_only_serial_identity_sample(self):
        scope = self.record["scope_boundary"]
        for field in (
            "two_distinct_assignment_ids_observed",
            "two_distinct_handoff_ids_observed",
            "two_distinct_child_thread_ids_observed",
            "two_distinct_canonical_agent_paths_observed",
            "serial_callback_before_next_spawn_observed",
            "subagentstop_correction_mediation_observed",
        ):
            self.assertTrue(scope[field])
        for field in (
            "both_records_fresh_owner_consumed",
            "nested_identity_cohort_qualified",
            "concurrent_identity_cohort_qualified",
            "resume_identity_cohort_qualified",
            "mutation_authority_granted",
            "strong_global_quiescence_qualified",
            "representative_latency_or_cost_cohort_qualified",
        ):
            self.assertFalse(scope[field])

    def test_every_promotion_remains_closed_and_no_credential_name_is_stored(self):
        verification = self.record["verification"]
        suite = verification["provider_free_suite"]
        self.assertEqual(suite["test_count"], 459)
        self.assertEqual(suite["exit_code"], 0)
        self.assertEqual(suite["agent_template_checks"], "passed")
        self.assertTrue(verification["phase1_gate_valid"])
        self.assertEqual(verification["phase1_gate_require_complete_exit_code"], 2)
        self.assertTrue(verification["mutation_matrix_valid"])
        self.assertEqual(verification["mutation_matrix_blocker_count"], 13)
        self.assertEqual(verification["mutation_matrix_require_qualified_exit_code"], 2)
        self.assertEqual(verification["same_uid_probe_exit_code"], 0)
        self.assertEqual(verification["same_uid_require_protected_exit_code"], 2)
        self.assertFalse(verification["same_uid_rollout_protected"])
        self.assertFalse(verification["same_uid_state_protected"])
        verdict = self.record["verdict"]
        self.assertTrue(verdict["serial_identity_positive_sample"])
        self.assertTrue(verdict["exact_sessionmeta_agentpath_binding_observed"])
        self.assertTrue(verdict["durable_reported_state_observed"])
        self.assertFalse(verdict["fresh_owner_adjudication_complete"])
        self.assertFalse(verdict["headless_candidate_exit_code_known"])
        self.assertFalse(verdict["direct_write_qualified"])
        self.assertFalse(verdict["phase1_complete"])
        self.assertFalse(verdict["phase2_open"])
        self.assertFalse(verdict["phase3_open"])
        self.assertNotIn("API_KEY", json.dumps(self.record, sort_keys=True))


if __name__ == "__main__":
    unittest.main()
