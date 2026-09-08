import json
from pathlib import Path
import re
import unittest
import uuid


ROOT = Path(__file__).resolve().parents[1]
RECORD = ROOT / "probes" / "g4-live-first-attestation-watchdog-cancel-race-20260908.json"
SHA256 = re.compile(r"^[0-9a-f]{64}$")


class G4LiveFirstAttestationWatchdogCancelRaceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.record = json.loads(RECORD.read_text(encoding="utf-8"))

    def test_default_namespace_control_remains_encrypted_and_fail_closed(self):
        control = self.record["encrypted_control_attempt"]

        self.assertEqual(control["tool_namespace"], "collaboration")
        self.assertEqual(control["message_prefix"], "gAAAAAB")
        self.assertEqual(control["authority_begin_count_at_pretool_input"], 0)
        self.assertEqual(control["authority_end_count_at_pretool_input"], 0)
        self.assertEqual(control["hook_decision"], "TASK.HANDOFF_BLOCKED")
        self.assertFalse(control["child_created"])
        self.assertFalse(control["qualification_succeeded"])
        self.assertRegex(control["parent_rollout_sha256"], SHA256)

    def test_plaintext_namespace_binds_exact_real_child_identity(self):
        live = self.record["plaintext_watchdog_attempt"]
        child = live["child"]
        authority = live["authority"]
        transport = live["transport"]

        self.assertEqual(transport["tool_namespace"], "g4_assignment")
        self.assertEqual(transport["message_delivery"], "plaintext")
        self.assertEqual(transport["authority_begin_count"], 1)
        self.assertEqual(transport["authority_end_count"], 1)
        uuid.UUID(child["thread_id"])
        uuid.UUID(authority["assignment_id"])
        self.assertNotEqual(child["thread_id"], authority["assignment_id"])
        self.assertEqual(child["runtime_session_id"], live["parent"]["thread_id"])
        self.assertEqual(child["parent_thread_id"], live["parent"]["thread_id"])
        self.assertEqual(child["canonical_agent_path"], "/root/g4_first_attestation_timeout_2")
        self.assertEqual(child["agent_type"], "g4_qualification_probe_worker")
        self.assertEqual(child["model_provider"], "openai")
        self.assertEqual(authority["assignment_mutation_mode"], "read_only")
        self.assertEqual(authority["owned_paths"], [])
        self.assertEqual(authority["excluded_paths"], [])
        self.assertFalse(any(authority["git_authority"].values()))

    def test_watchdog_fires_before_any_git_attestation_or_child_tool(self):
        live = self.record["plaintext_watchdog_attempt"]
        child = live["child"]
        authority = live["authority"]
        watchdog = live["watchdog"]

        self.assertEqual(child["native_tool_call_count"], 0)
        self.assertIsNone(child["first_git_attested_at"])
        self.assertGreater(watchdog["observed_at"], authority["pre_write_attestation_deadline"])
        self.assertLess(watchdog["observed_at"], authority["expires_at"])
        self.assertEqual(watchdog["selection"], "exact")
        self.assertEqual(watchdog["requested_assignment_ids"], [authority["assignment_id"]])
        self.assertEqual(watchdog["exit_code"], 2)
        self.assertTrue(watchdog["valid"])
        self.assertEqual(watchdog["terminated_count"], 1)
        self.assertTrue(watchdog["parent_cancel_required"])
        self.assertEqual(watchdog["reason"], "pre_write_attestation_timeout")
        self.assertEqual(watchdog["classification"], "unresponsive_no_disk_change")
        self.assertTrue(watchdog["baseline_comparable"])
        self.assertFalse(watchdog["disk_changed"])
        self.assertEqual(watchdog["snapshot"]["git_status_short"], "")
        self.assertEqual(watchdog["snapshot"]["changed_paths"], [])
        self.assertEqual(authority["state_bucket_after_watchdog"], "unresolved")

    def test_hook_chain_captures_spawn_start_and_three_stop_attempts(self):
        receipts = self.record["plaintext_watchdog_attempt"]["hook_receipts"]

        self.assertEqual([item["sequence"] for item in receipts], list(range(1491, 1496)))
        self.assertEqual([item["event"] for item in receipts], [
            "PreToolUse",
            "SubagentStart",
            "SubagentStop",
            "SubagentStop",
            "SubagentStop",
        ])
        for receipt in receipts:
            self.assertRegex(receipt["receipt_sha256"], SHA256)

    def test_parent_interrupt_loses_the_post_watchdog_completion_race(self):
        live = self.record["plaintext_watchdog_attempt"]
        child = live["child"]
        race = live["cancel_race"]

        self.assertGreater(race["interrupt_called_at"], child["task_complete_at"])
        self.assertEqual(
            race["interrupt_previous_status"],
            {"completed": "WAITING_FOR_PARENT_INTERRUPT"},
        )
        self.assertEqual(race["list_agents_child_status"], race["interrupt_previous_status"])
        self.assertGreater(race["child_completed_before_interrupt_seconds"], 0)
        self.assertFalse(race["running_child_interrupt_acknowledged"])

    def test_follow_up_guard_is_implemented_but_not_live_qualified(self):
        mechanism = self.record["follow_up_mechanism"]
        verdict = self.record["scope_verdict"]

        self.assertEqual(mechanism["parent_cancel_required_reasons"], [
            "assignment_timeout",
            "pre_write_attestation_timeout",
        ])
        self.assertIn("TASK.PARENT_CANCEL_REQUIRED", mechanism["subagentstop_behavior"])
        self.assertGreaterEqual(mechanism["related_tests_passed"], 120)
        self.assertFalse(mechanism["installed_live_at_receipt_time"])
        self.assertFalse(mechanism["live_revalidated"])
        self.assertTrue(verdict["live_pre_write_attestation_deadline_observed"])
        self.assertTrue(verdict["live_exact_watchdog_transition_observed"])
        self.assertTrue(verdict["cancel_race_reproduced"])
        self.assertTrue(verdict["isolated_cancel_race_guard_implemented"])
        self.assertFalse(verdict["isolated_cancel_race_guard_live_qualified"])
        self.assertFalse(verdict["strong_termination_quiescence_qualified"])
        self.assertFalse(verdict["phase1_complete"])
        self.assertFalse(verdict["direct_write_qualified"])
        self.assertFalse(verdict["phase2_open"])
        self.assertFalse(verdict["phase3_open"])

    def test_fresh_provider_free_verification_stays_fail_closed(self):
        verification = self.record["verification"]

        self.assertEqual(verification["targeted_test_count"], 72)
        self.assertEqual(verification["full_provider_free_test_count"], 515)
        self.assertTrue(verification["agent_template_checks_passed"])
        self.assertEqual(verification["phase1_gate_exit_code"], 0)
        self.assertEqual(verification["phase1_promotion_exit_code"], 2)
        self.assertEqual(verification["mutation_gate_exit_code"], 0)
        self.assertEqual(verification["mutation_promotion_exit_code"], 2)
        self.assertEqual(verification["same_uid_gate_exit_code"], 0)
        self.assertEqual(verification["same_uid_promotion_exit_code"], 2)
        self.assertEqual(verification["mutation_blocker_count"], 13)
        self.assertFalse(verification["same_uid_rollout_protected"])
        self.assertFalse(verification["same_uid_state_protected"])


if __name__ == "__main__":
    unittest.main()
