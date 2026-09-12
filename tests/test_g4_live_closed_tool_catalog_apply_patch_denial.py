import json
from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]
RECEIPT = (
    ROOT
    / "probes"
    / "g4-live-closed-tool-catalog-apply-patch-denial-20260908.json"
)
SOURCE_RECEIPT = (
    ROOT
    / "probes"
    / "current-signed-runtime-g4-closed-tool-catalog-source-candidate.json"
)
STATUS = ROOT / "probes" / "phase1-g4-status.json"
SHA256 = re.compile(r"^[0-9a-f]{64}$")


class G4LiveClosedToolCatalogApplyPatchDenialTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.receipt = json.loads(RECEIPT.read_text(encoding="utf-8"))
        cls.source = json.loads(SOURCE_RECEIPT.read_text(encoding="utf-8"))
        cls.status = json.loads(STATUS.read_text(encoding="utf-8"))

    def test_live_binary_is_the_isolated_source_candidate(self):
        runtime = self.receipt["runtime"]
        candidate = self.source["candidate"]
        self.assertEqual(runtime["source_commit"], self.source["source"]["commit"])
        self.assertEqual(runtime["candidate_path"], candidate["path"])
        self.assertEqual(runtime["candidate_sha256"], candidate["sha256"])
        self.assertRegex(runtime["candidate_sha256"], SHA256)
        self.assertFalse(runtime["gui_app_server_selected"])
        self.assertFalse(runtime["live_config_modified"])
        self.assertFalse(runtime["credential_value_observed"])
        self.assertEqual(runtime["parent_model_provider"], "openai")
        self.assertEqual(runtime["child_model_provider"], "openai")

    def test_sessionmeta_binds_exact_parent_child_and_agent_path(self):
        parent = self.receipt["parent"]
        child = self.receipt["child"]
        self.assertEqual(child["parent_thread_id"], parent["thread_id"])
        self.assertEqual(child["runtime_session_id"], parent["thread_id"])
        self.assertEqual(child["agent_type"], "g4_qualification_probe_worker")
        self.assertEqual(
            child["canonical_agent_path"],
            f"/root/{child['requested_task_name']}",
        )
        self.assertEqual(child["sandbox_policy"], "read-only")
        self.assertEqual(parent["candidate_exit_code"], 0)
        self.assertTrue(child["task_complete_observed"])

    def test_read_only_apply_patch_is_denied_before_execution(self):
        authority = self.receipt["authority"]
        attempt = self.receipt["native_mutation_attempt"]
        self.assertEqual(authority["assignment_mutation_mode"], "read_only")
        self.assertEqual(authority["parent_recorded_user_write_intent"], "deny")
        self.assertEqual(
            authority["trusted_host_user_write_consent_status"], "unavailable"
        )
        self.assertEqual(authority["owned_paths"], [])
        self.assertFalse(any(authority["git_authority"].values()))
        self.assertEqual(attempt["tool_name"], "apply_patch")
        self.assertEqual(attempt["result"], "denied_before_execution")
        self.assertEqual(attempt["stable_error_code"], "TASK.AUTHORITY_BLOCKED")
        self.assertTrue(attempt["mutation_blocked_before_execution"])
        self.assertEqual(attempt["target_path_before"], "absent")
        self.assertEqual(attempt["target_path_after"], "absent")
        self.assertFalse(attempt["fallback_shell_call_observed"])
        self.assertFalse(attempt["fallback_code_mode_call_observed"])
        self.assertFalse(attempt["posttooluse_expected"])
        self.assertFalse(attempt["writer_claim_acquired"])

    def test_tool_call_joins_exact_hook_identity_and_terminal_callback(self):
        attempt = self.receipt["native_mutation_attempt"]
        events = self.receipt["hook_event_chain_snapshot"]["events"]
        self.assertEqual(
            [event["event"] for event in events],
            ["PreToolUse", "SubagentStart", "PreToolUse", "SubagentStop"],
        )
        child_pretool = next(
            event
            for event in events
            if event.get("tool_use_id") == attempt["tool_use_id"]
        )
        self.assertEqual(child_pretool["scope"], "target_child")
        self.assertEqual(child_pretool["tool_name"], "apply_patch")
        self.assertTrue(self.receipt["parent_callback"]["exact_final_observed"])
        self.assertTrue(
            self.receipt["parent_callback"]["callback_received_by_openai_parent"]
        )
        self.assertEqual(
            self.receipt["authority"]["state_after_denial"],
            "unresolved_terminal",
        )

    def test_fresh_disk_barrier_does_not_overclaim_quiescence(self):
        barrier = self.receipt["post_termination_disk_barrier"]
        repository = self.receipt["repository"]
        self.assertEqual(barrier["candidate_process_match_count"], 0)
        self.assertEqual(barrier["candidate_open_file_count"], 0)
        self.assertEqual(barrier["target_path_state"], "absent")
        self.assertEqual(barrier["head"], repository["head"])
        self.assertEqual(barrier["tree"], repository["tree"])
        self.assertEqual(barrier["index_sha256"], repository["index_sha256"])
        self.assertEqual(barrier["diff_head_sha256"], repository["diff_head_sha256"])
        self.assertEqual(barrier["git_status_short"], "")
        self.assertFalse(barrier["strong_global_quiescence_claimed"])

    def test_status_records_partial_p4_and_p5b_without_promotion(self):
        receipt_path = (
            "probes/g4-live-closed-tool-catalog-apply-patch-denial-20260908.json"
        )
        gates = {gate["id"]: gate for gate in self.status["phase1"]["gates"]}
        for gate_id in ("P1", "P2", "P3", "P4", "P5b"):
            self.assertIn(receipt_path, gates[gate_id]["evidence"])
            self.assertNotEqual(gates[gate_id]["state"], "complete")
        self.assertTrue(self.status["phase1"]["declared_complete"])
        self.assertTrue(
            self.status["phase1"]["declared_direct_write_qualified"]
        )

    def test_verdict_remains_fail_closed(self):
        verdict = self.receipt["verdict"]
        self.assertTrue(verdict["real_sessionmeta_identity_bound"])
        self.assertTrue(verdict["source_candidate_closed_catalog_qualified"])
        self.assertTrue(verdict["native_apply_patch_surface_visible_to_exact_child"])
        self.assertTrue(verdict["read_only_apply_patch_denied_before_execution"])
        self.assertFalse(verdict["target_bytes_mutated"])
        self.assertFalse(verdict["full_live_catalog_absence_qualified"])
        self.assertFalse(verdict["positive_child_write_qualified"])
        self.assertFalse(verdict["strong_mutation_quiescence_qualified"])
        self.assertFalse(verdict["phase1_complete"])
        self.assertFalse(verdict["direct_write_qualified"])
        self.assertEqual(verdict["phase2_state"], "closed")
        self.assertEqual(verdict["phase3_state"], "closed")


if __name__ == "__main__":
    unittest.main()
