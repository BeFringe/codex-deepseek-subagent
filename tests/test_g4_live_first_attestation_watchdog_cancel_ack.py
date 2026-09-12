import json
from pathlib import Path
import re
import unittest
import uuid


ROOT = Path(__file__).resolve().parents[1]
RECORD = ROOT / "probes" / "g4-live-first-attestation-watchdog-cancel-ack-20260908.json"
STATUS = ROOT / "probes" / "phase1-g4-status.json"
SHA256 = re.compile(r"^[0-9a-f]{64}$")


class G4LiveFirstAttestationWatchdogCancelAckTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.record = json.loads(RECORD.read_text(encoding="utf-8"))

    def test_exact_installed_guard_is_bound_without_gui_app_server_replacement(self):
        runtime = self.record["runtime"]
        install = self.record["live_hook_install"]

        self.assertEqual(
            install["repository_runtime_guard_sha256"],
            install["installed_runtime_guard_sha256"],
        )
        self.assertNotEqual(
            install["installed_runtime_guard_sha256"],
            install["prior_runtime_guard_sha256"],
        )
        self.assertEqual(install["backup_sha256"], install["prior_runtime_guard_sha256"])
        for key in (
            "repository_runtime_guard_sha256",
            "installed_runtime_guard_sha256",
            "prior_runtime_guard_sha256",
            "backup_sha256",
            "hooks_json_sha256",
        ):
            self.assertRegex(install[key], SHA256)
        self.assertFalse(runtime["gui_app_server_selected"])
        self.assertFalse(runtime["live_config_modified"])
        self.assertFalse(runtime["credential_value_observed"])
        self.assertFalse(install["new_hook_trust_prompt_observed"])

    def test_plaintext_assignment_binds_exact_sessionmeta_and_agentpath(self):
        parent = self.record["parent"]
        transport = self.record["transport"]
        child = self.record["child"]
        authority = self.record["authority"]

        uuid.UUID(parent["thread_id"])
        uuid.UUID(child["thread_id"])
        uuid.UUID(authority["assignment_id"])
        uuid.UUID(authority["handoff_id"])
        self.assertEqual(transport["tool_namespace"], "g4_assignment")
        self.assertEqual(transport["message_delivery"], "plaintext")
        self.assertEqual(transport["authority_begin_count"], 1)
        self.assertEqual(transport["authority_end_count"], 1)
        self.assertEqual(transport["spawn_projection"]["task_name"], child["canonical_agent_path"])
        self.assertEqual(child["parent_thread_id"], parent["thread_id"])
        self.assertEqual(child["runtime_session_id"], parent["thread_id"])
        self.assertEqual(child["canonical_agent_path"], "/root/g4_first_attestation_timeout_3")
        self.assertEqual(child["agent_type"], "g4_qualification_probe_worker")
        self.assertEqual(child["model_provider"], "openai")
        self.assertEqual(authority["assignment_mutation_mode"], "read_only")
        self.assertEqual(authority["owned_paths"], [])
        self.assertEqual(authority["excluded_paths"], [])
        self.assertFalse(any(authority["git_authority"].values()))

    def test_watchdog_fires_without_child_tool_or_git_attestation(self):
        child = self.record["child"]
        authority = self.record["authority"]
        watchdog = self.record["watchdog"]

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

    def test_timeout_terminal_final_is_held_for_parent_cancel(self):
        watchdog = self.record["watchdog"]
        stop = self.record["subagent_stop_gate"]

        self.assertEqual(
            [item["decision"] for item in stop["hook_observations"]],
            [
                "TASK.FINAL_INVALID_FINAL_WITHOUT_CONTRIBUTION",
                "TASK.FINAL_INVALID_FINAL_WITHOUT_CONTRIBUTION",
                "TASK.PARENT_CANCEL_REQUIRED",
            ],
        )
        self.assertGreater(stop["hook_observations"][-1]["observed_at"], watchdog["observed_at"])
        self.assertTrue(stop["timeout_terminal_final_held"])
        self.assertFalse(stop["child_self_completion_after_watchdog"])

    def test_native_interrupt_acknowledges_running_child_then_lists_interrupted(self):
        child = self.record["child"]
        cancellation = self.record["cancellation"]

        self.assertGreater(cancellation["interrupt_called_at"], self.record["watchdog"]["observed_at"])
        self.assertEqual(cancellation["interrupt_previous_status"], "running")
        self.assertGreater(child["turn_aborted_at"], cancellation["interrupt_called_at"])
        self.assertEqual(child["turn_aborted_reason"], "interrupted")
        self.assertFalse(child["task_complete_observed"])
        self.assertFalse(child["accepted_final_observed"])
        self.assertEqual(cancellation["list_agents_child_status"], "interrupted")
        self.assertTrue(cancellation["running_child_interrupt_acknowledged"])
        self.assertFalse(cancellation["strong_host_termination_receipt_observed"])
        self.assertFalse(cancellation["mutation_quiescence_receipt_observed"])

    def test_hook_chain_is_contiguous_and_payload_minimized(self):
        chain = self.record["hook_chain"]
        receipts = chain["target_receipts"]

        self.assertEqual([item["sequence"] for item in receipts], list(range(1538, 1543)))
        self.assertEqual(
            [item["hook_event_name"] for item in receipts],
            ["PreToolUse", "SubagentStart", "SubagentStop", "SubagentStop", "SubagentStop"],
        )
        self.assertEqual(chain["event_count"], receipts[-1]["sequence"])
        self.assertEqual(chain["head_receipt_sha256"], receipts[-1]["receipt_sha256"])
        self.assertFalse(chain["raw_payload_stored"])
        for key in ("snapshot_sha256", "chain_sha256", "head_receipt_sha256"):
            self.assertRegex(chain[key], SHA256)
        for receipt in receipts:
            self.assertRegex(receipt["receipt_sha256"], SHA256)

    def test_p5a_signal_is_qualified_without_promoting_p5b_or_phase1(self):
        barrier = self.record["post_interrupt_barrier"]
        verification = self.record["verification"]
        verdict = self.record["scope_verdict"]

        self.assertEqual(barrier["candidate_process_open_file_count"], 0)
        self.assertEqual(barrier["repository_status"], "clean")
        self.assertEqual(barrier["assignment_buckets"]["unresolved"], "present")
        for bucket in ("active", "claimed", "pending", "reported", "consumed"):
            self.assertEqual(barrier["assignment_buckets"][bucket], "absent")
        self.assertFalse(barrier["ownership_handover_authorized"])
        self.assertTrue(verdict["p5a_current_runtime_signal_qualified"])
        self.assertFalse(verdict["p5b_strong_termination_quiescence_qualified"])
        self.assertFalse(verdict["ownership_handover_authorized"])
        self.assertFalse(verdict["phase1_complete"])
        self.assertFalse(verdict["direct_write_qualified"])
        self.assertFalse(verdict["phase2_open"])
        self.assertFalse(verdict["phase3_open"])
        self.assertEqual(verification["focused_test_count"], 79)
        self.assertEqual(verification["full_provider_free_test_count"], 522)
        self.assertTrue(verification["agent_template_checks_passed"])
        self.assertEqual(verification["phase1_gate_exit_code"], 0)
        self.assertEqual(verification["phase1_promotion_exit_code"], 2)
        self.assertEqual(verification["p5a_status"], "qualified")
        self.assertEqual(verification["p5b_status"], "partial")

        status = json.loads(STATUS.read_text(encoding="utf-8"))
        gates = {gate["id"]: gate for gate in status["phase1"]["gates"]}
        self.assertEqual(gates["P5a"]["state"], "qualified")
        self.assertEqual(gates["P5a"]["provider_free"], "pass")
        self.assertEqual(gates["P5b"]["state"], "qualified")
        self.assertFalse(status["phase1"]["declared_complete"])
        self.assertFalse(status["phase1"]["declared_direct_write_qualified"])


if __name__ == "__main__":
    unittest.main()
