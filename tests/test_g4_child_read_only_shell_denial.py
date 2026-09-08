import json
from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]
RECORD = ROOT / "probes" / "g4-child-read-only-shell-denial-20260908.json"
SHA256 = re.compile(r"^[0-9a-f]{64}$")


class G4ChildReadOnlyShellDenialTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.record = json.loads(RECORD.read_text(encoding="utf-8"))

    def test_probe_binds_exact_child_identity_and_read_only_authority(self):
        probe = self.record["live_probe"]
        self.assertEqual(probe["parent_thread_id"], probe["runtime_session_id"])
        self.assertEqual(probe["canonical_agent_path"], "/root/g4_child_shell_deny_1")
        self.assertEqual(probe["assignment_mutation_mode"], "read_only")
        self.assertEqual(probe["trusted_host_user_write_consent_status"], "unavailable")
        for field in (
            "capsule_sha256",
            "compact_invariant_sha256",
            "parent_rollout_sha256",
            "child_rollout_sha256",
            "unresolved_state_sha256",
        ):
            self.assertTrue(SHA256.fullmatch(probe[field]))

    def test_hook_chain_is_one_spawn_start_bash_stop_sequence(self):
        chain = self.record["live_probe"]["hook_event_chain"]
        self.assertEqual([event["sequence"] for event in chain], list(range(1293, 1297)))
        self.assertEqual(
            [event["hook_event_name"] for event in chain],
            ["PreToolUse", "SubagentStart", "PreToolUse", "SubagentStop"],
        )
        self.assertEqual(chain[2]["tool_name"], "Bash")
        for event in chain:
            self.assertTrue(SHA256.fullmatch(event["receipt_sha256"]))

    def test_nested_exec_command_is_observed_as_bash_and_denied(self):
        attempt = self.record["live_probe"]["nested_shell_attempt"]
        self.assertEqual(attempt["requested_nested_api"], "tools.exec_command")
        self.assertEqual(attempt["observed_native_hook_tool_name"], "Bash")
        self.assertFalse(attempt["shell_composition"])
        self.assertEqual(attempt["result"], "denied_before_process_execution")
        self.assertEqual(attempt["stable_error_code"], "TASK.AUTHORITY_BLOCKED")
        self.assertEqual(attempt["target_path_before"], "absent")
        self.assertEqual(attempt["target_path_after"], "absent")

    def test_termination_evidence_proves_no_pre_attempt_disk_change(self):
        evidence = self.record["live_probe"]["termination_evidence"]
        self.assertEqual(evidence["reason"], "read_only_mutation_attempt")
        self.assertEqual(evidence["attempted_tool_name"], "Bash")
        self.assertTrue(evidence["mutation_blocked_before_execution"])
        self.assertTrue(evidence["baseline_comparable"])
        self.assertFalse(evidence["disk_changed"])
        self.assertEqual(evidence["snapshot"]["git_status_short"], "")
        self.assertEqual(evidence["snapshot"]["changed_paths"], [])

    def test_single_stop_and_parent_callback_complete(self):
        lifecycle = self.record["live_probe"]["lifecycle"]
        self.assertEqual(lifecycle["subagent_stop_observation_count"], 1)
        self.assertEqual(lifecycle["correction_prompt_count"], 0)
        self.assertTrue(lifecycle["child_task_complete"])
        self.assertTrue(lifecycle["parent_observed_exact_final_callback"])
        self.assertTrue(lifecycle["parent_task_complete"])
        self.assertEqual(lifecycle["headless_process_exit_code"], 0)
        self.assertEqual(lifecycle["authority_state_after_stop"], "unresolved_terminal")
        self.assertFalse(lifecycle["promoted_to_reported_or_consumed"])

    def test_scope_does_not_overclaim_bootstrap_sandbox_or_quiescence(self):
        scope = self.record["scope_boundary"]
        self.assertFalse(scope["app_server_bootstrap_command_executed"])
        self.assertFalse(scope["external_same_uid_process_bootstrap_blocked"])
        self.assertFalse(scope["sandbox_enforcement_reached"])
        barrier = self.record["live_probe"]["post_termination_disk_barrier"]
        self.assertEqual(barrier["candidate_process_match_count"], 0)
        self.assertEqual(barrier["target_path_state"], "absent")
        self.assertFalse(barrier["strong_global_quiescence_claimed"])

    def test_fresh_provider_free_regression_and_gates_remain_fail_closed(self):
        verification = self.record["verification"]
        suite = verification["provider_free_suite"]
        self.assertEqual(suite["test_count"], 429)
        self.assertEqual(suite["exit_code"], 0)
        self.assertEqual(suite["agent_template_checks"], "passed")
        self.assertTrue(verification["phase1_gate_valid"])
        self.assertTrue(verification["mutation_matrix_valid"])
        self.assertEqual(verification["mutation_matrix_blocker_count"], 13)
        self.assertFalse(verification["same_uid_rollout_protected"])
        self.assertFalse(verification["same_uid_state_protected"])

    def test_verdict_keeps_every_promotion_closed(self):
        verdict = self.record["verdict"]
        self.assertTrue(verdict["read_only_child_bash_denied_before_process_execution"])
        self.assertTrue(verdict["exact_sessionmeta_agentpath_binding_observed"])
        self.assertTrue(verdict["terminal_callback_observed"])
        for field in (
            "target_bytes_mutated",
            "child_write_authority_granted",
            "git_authority_granted",
            "full_shell_negative_space_qualified",
            "appserver_host_control_bootstrap_qualified",
            "trusted_sandbox_boundary_qualified",
            "strong_global_quiescence_qualified",
            "direct_write_qualified",
            "phase1_complete",
            "phase2_open",
            "phase3_open",
        ):
            self.assertFalse(verdict[field])


if __name__ == "__main__":
    unittest.main()
