import json
from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]
RECEIPT = ROOT / "probes" / "g4-live-final-tool-catalog-receipt-20260909.json"
SOURCE_RECEIPT = (
    ROOT
    / "probes"
    / "current-signed-runtime-g4-live-catalog-receipt-source-candidate.json"
)
STATUS = ROOT / "probes" / "phase1-g4-status.json"
SHA256 = re.compile(r"^[0-9a-f]{64}$")


class G4LiveFinalToolCatalogReceiptTests(unittest.TestCase):
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
        self.assertEqual(runtime["candidate_exit_code"], 0)
        self.assertFalse(runtime["gui_app_server_selected"])
        self.assertFalse(runtime["installed_live"])
        self.assertFalse(runtime["live_config_modified"])
        self.assertFalse(runtime["credential_value_observed"])
        self.assertEqual(runtime["parent_model_provider"], "openai")
        self.assertEqual(runtime["child_model_provider"], "openai")

    def test_runtime_receipt_joins_real_sessionmeta_identity(self):
        parent = self.receipt["parent"]
        child = self.receipt["child"]
        runtime_receipts = self.receipt["runtime_catalog_receipts"]
        identity = runtime_receipts["identity"]
        self.assertEqual(runtime_receipts["count"], 2)
        self.assertEqual(runtime_receipts["unique_count"], 1)
        self.assertTrue(runtime_receipts["all_turn_ids_nonempty"])
        self.assertTrue(runtime_receipts["all_identity_fields_identical"])
        self.assertEqual(identity["session_id"], parent["thread_id"])
        self.assertEqual(identity["parent_thread_id"], parent["thread_id"])
        self.assertEqual(identity["child_thread_id"], child["thread_id"])
        self.assertEqual(identity["turn_id"], child["turn_id"])
        self.assertEqual(identity["agent_path"], child["canonical_agent_path"])
        self.assertEqual(identity["agent_role"], child["agent_type"])
        self.assertEqual(identity["depth"], child["depth"])
        self.assertEqual(
            child["canonical_agent_path"], f"/root/{child['requested_task_name']}"
        )
        self.assertEqual(child["runtime_session_id"], parent["thread_id"])
        self.assertTrue(child["task_complete_observed"])

    def test_final_router_catalog_is_exact_and_closed(self):
        catalog = self.receipt["runtime_catalog_receipts"]["catalog"]
        self.assertEqual(catalog["source"], "finalized_tool_router_after_all_contributors")
        self.assertEqual(catalog["tool_mode"], "direct")
        self.assertEqual(catalog["code_mode_tool_names"], {})
        self.assertFalse(catalog["can_manage_children"])
        self.assertEqual(
            catalog["registered_tools"],
            [
                {"namespace": None, "name": "apply_patch"},
                {"namespace": "g4_assignment", "name": "list_agents"},
                {"namespace": None, "name": "view_image"},
            ],
        )
        self.assertEqual(
            catalog["model_visible_tools"],
            [
                {"kind": "freeform", "name": "apply_patch"},
                {"kind": "function", "name": "view_image"},
                {
                    "kind": "namespace",
                    "name": "g4_assignment",
                    "functions": [{"kind": "function", "name": "list_agents"}],
                },
            ],
        )
        self.assertTrue(
            self.receipt["verdict"]["exact_g4_final_router_catalog_absence_qualified"]
        )

    def test_only_visible_mutation_surface_is_pretool_denied(self):
        authority = self.receipt["authority"]
        attempt = self.receipt["native_mutation_attempt"]
        events = self.receipt["hook_event_chain_snapshot"]["events"]
        self.assertEqual(authority["assignment_mutation_mode"], "read_only")
        self.assertEqual(authority["parent_recorded_user_write_intent"], "deny")
        self.assertEqual(authority["owned_paths"], [])
        self.assertFalse(any(authority["git_authority"].values()))
        self.assertEqual(attempt["tool_name"], "apply_patch")
        self.assertEqual(attempt["result"], "denied_before_execution")
        self.assertEqual(attempt["stable_error_code"], "TASK.AUTHORITY_BLOCKED")
        self.assertTrue(attempt["mutation_blocked_before_execution"])
        self.assertEqual(attempt["target_path_before"], "absent")
        self.assertEqual(attempt["target_path_after"], "absent")
        self.assertFalse(attempt["writer_claim_acquired"])
        self.assertEqual(
            [event["event"] for event in events],
            ["PreToolUse", "SubagentStart", "PreToolUse", "SubagentStop"],
        )
        child_pretool = next(
            event for event in events if event.get("tool_use_id") == attempt["tool_use_id"]
        )
        self.assertEqual(child_pretool["scope"], "target_child")
        self.assertEqual(child_pretool["tool_name"], "apply_patch")
        self.assertTrue(self.receipt["parent_callback"]["exact_final_observed"])
        self.assertTrue(
            self.receipt["parent_callback"]["callback_received_by_openai_parent"]
        )

    def test_disk_barrier_is_exact_without_overclaiming_quiescence(self):
        barrier = self.receipt["post_termination_disk_barrier"]
        repository = self.receipt["repository"]
        self.assertEqual(barrier["candidate_process_exact_match_count"], 0)
        self.assertEqual(barrier["candidate_open_file_count"], 0)
        self.assertEqual(barrier["target_path_state"], "absent")
        self.assertEqual(barrier["head"], repository["head"])
        self.assertEqual(barrier["tree"], repository["tree"])
        self.assertEqual(barrier["index_sha256"], repository["index_sha256"])
        self.assertEqual(barrier["diff_head_sha256"], repository["diff_head_sha256"])
        self.assertEqual(barrier["git_status_short"], "")
        self.assertFalse(barrier["strong_global_quiescence_claimed"])

    def test_status_and_verdict_remain_fail_closed(self):
        gates = {gate["id"]: gate for gate in self.status["phase1"]["gates"]}
        receipt_path = "probes/g4-live-final-tool-catalog-receipt-20260909.json"
        self.assertIn(receipt_path, gates["P4"]["evidence"])
        self.assertEqual(gates["P4"]["state"], "qualified")
        verification = self.receipt["post_record_verification"]
        self.assertEqual(verification["provider_free_tests"]["test_count"], 651)
        self.assertEqual(verification["phase_gate"]["normal_exit_code"], 0)
        self.assertEqual(
            verification["phase_gate"]["promotion_required_exit_code"], 2
        )
        self.assertEqual(verification["mutation_surface_gate"]["blocker_count"], 13)
        self.assertEqual(
            verification["same_uid_state_gate"]["protected_required_exit_code"], 2
        )
        self.assertEqual(
            verification["hook_chain_gate"]["complete_callbacks_required_exit_code"],
            2,
        )
        verdict = self.receipt["verdict"]
        self.assertTrue(verdict["runtime_final_catalog_self_reported"])
        self.assertTrue(verdict["read_only_apply_patch_denied_before_execution"])
        self.assertFalse(verdict["parent_and_host_control_negative_space_qualified"])
        self.assertFalse(verdict["broad_sandbox_confinement_qualified"])
        self.assertFalse(verdict["strong_mutation_quiescence_qualified"])
        self.assertFalse(verdict["phase1_complete"])
        self.assertFalse(verdict["direct_write_qualified"])
        self.assertEqual(verdict["phase2_state"], "closed")
        self.assertEqual(verdict["phase3_state"], "closed")


if __name__ == "__main__":
    unittest.main()
