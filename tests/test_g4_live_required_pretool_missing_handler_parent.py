import json
from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]
RECEIPT = (
    ROOT
    / "probes"
    / "g4-live-required-pretool-missing-handler-parent-20260909.json"
)
SOURCE = (
    ROOT
    / "probes"
    / "current-signed-runtime-g4-required-pretool-fail-closed-source-candidate.json"
)
RUNTIME_INDEX = ROOT / "probes" / "codex-runtime-evidence-index.json"
STATUS = ROOT / "probes" / "phase1-g4-status.json"
WRAPPER = ROOT / "probes" / "codex_plaintext_candidate_wrapper.sh"
SHA256 = re.compile(r"^[0-9a-f]{64}$")


class G4LiveRequiredPreToolMissingHandlerParentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.receipt = json.loads(RECEIPT.read_text(encoding="utf-8"))
        cls.source = json.loads(SOURCE.read_text(encoding="utf-8"))
        cls.runtime_index = json.loads(RUNTIME_INDEX.read_text(encoding="utf-8"))
        cls.status = json.loads(STATUS.read_text(encoding="utf-8"))
        cls.wrapper = WRAPPER.read_text(encoding="utf-8")

    def test_runtime_identity_is_current_hash_pinned_headless_candidate(self):
        runtime = self.receipt["runtime"]
        current_role = self.runtime_index["current_runtime_role"]
        current = self.runtime_index["runtime_roles"][current_role]
        self.assertEqual(runtime["source_commit"], current["source_commit"])
        self.assertEqual(runtime["codex_cli_version"], current["codex_version"])
        self.assertEqual(runtime["source_receipt"], SOURCE.relative_to(ROOT).as_posix())
        self.assertRegex(runtime["candidate_sha256"], SHA256)
        self.assertGreater(runtime["candidate_bytes"], 0)
        self.assertEqual(runtime["candidate_exit_code"], 0)
        self.assertFalse(runtime["gui_app_server_selected"])
        self.assertFalse(runtime["installed_live"])
        self.assertFalse(runtime["credential_value_observed"])
        self.assertEqual(runtime["model_provider"], "openai")

    def test_wrapper_guard_is_read_only_headless_and_does_not_modify_global_hooks(self):
        isolation = self.receipt["isolation"]
        self.assertEqual(
            isolation["wrapper_guard"], "schema1-exact-missing-handler-parent"
        )
        self.assertIn("CODEX_G4_REQUIRED_PRETOOL_PROBE_AUTHORIZED", self.wrapper)
        self.assertIn("required_pretool_config=features.hooks=false", self.wrapper)
        self.assertFalse(isolation["hooks_feature_for_this_process"])
        self.assertFalse(isolation["global_hooks_json_modified"])
        self.assertEqual(
            isolation["global_hooks_json_sha256_before"],
            isolation["global_hooks_json_sha256_after"],
        )
        self.assertFalse(isolation["global_app_server_selection_modified"])
        self.assertFalse(isolation["user_approval_prompt_observed"])

    def test_real_parent_identity_and_closed_catalog_are_exact(self):
        identity = self.receipt["identity"]
        catalog = self.receipt["runtime_catalog_receipts"]
        self.assertEqual(identity["session_id"], identity["thread_id"])
        self.assertEqual(identity["agent_path"], "/root")
        self.assertEqual(identity["agent_role"], "root")
        self.assertEqual(identity["session_source"], "exec")
        self.assertRegex(identity["prompt_sha256"], SHA256)
        self.assertEqual(catalog["count"], 2)
        self.assertEqual(catalog["unique_count"], 1)
        self.assertTrue(catalog["all_identity_fields_identical"])
        self.assertEqual(catalog["tool_mode"], "direct")
        self.assertEqual(catalog["code_mode_tool_names"], {})
        self.assertTrue(catalog["can_manage_children"])
        self.assertIn("view_image", catalog["registered_tools"])

    def test_single_real_tool_call_is_denied_before_handler(self):
        attempt = self.receipt["native_tool_attempt"]
        barrier = self.receipt["disk_barrier"]
        self.assertEqual(attempt["tool_name"], "view_image")
        self.assertEqual(attempt["function_call_count"], 1)
        self.assertEqual(attempt["function_call_output_count"], 1)
        self.assertEqual(attempt["other_tool_call_count"], 0)
        self.assertEqual(attempt["matching_control_handlers"], 0)
        self.assertEqual(attempt["adjudicated_control_handlers"], 0)
        self.assertEqual(attempt["result"], "denied_before_tool_handler")
        self.assertEqual(
            attempt["exact_result"],
            "Qualification PreToolUse mediation unavailable: matched 0 control "
            "handler(s), adjudicated 0. Tool: view_image",
        )
        self.assertEqual(attempt["hook_started_or_completed_event_count"], 0)
        self.assertEqual(barrier["tree"], "4b825dc642cb6eb9a060e54bf8d69288fbee4904")
        self.assertEqual(barrier["git_status_short"], "")
        self.assertEqual(barrier["target_before"], "absent")
        self.assertEqual(barrier["target_after"], "absent")
        self.assertEqual(barrier["candidate_process_exact_match_count"], 0)
        self.assertEqual(barrier["candidate_open_file_count"], 0)
        self.assertFalse(barrier["strong_global_quiescence_claimed"])

    def test_raw_artifacts_are_hash_and_size_bound_without_promotion(self):
        raw = self.receipt["raw_runtime"]
        for kind in ("events", "stderr", "final", "rollout"):
            self.assertRegex(raw[f"{kind}_sha256"], SHA256)
            self.assertGreaterEqual(raw[f"{kind}_lines"], 0)
            self.assertGreater(raw[f"{kind}_bytes"], 0)
        self.assertTrue(raw["stored_outside_repository"])
        self.assertFalse(raw["raw_payload_committed"])
        verification = self.receipt["post_record_verification"]
        self.assertEqual(verification["provider_free_suite"]["test_count"], 770)
        self.assertEqual(verification["provider_free_suite"]["result"], "pass")
        self.assertEqual(verification["phase1_normal_exit"], 0)
        self.assertEqual(verification["phase1_required_exit"], 2)
        self.assertEqual(verification["mutation_normal_exit"], 0)
        self.assertEqual(verification["mutation_required_exit"], 2)
        self.assertEqual(verification["same_uid_normal_exit"], 0)
        self.assertEqual(verification["same_uid_required_exit"], 2)
        self.assertEqual(verification["semantic_runtime_index_exit"], 0)
        verdict = self.receipt["verdict"]
        self.assertTrue(verdict["exact_parent_missing_handler_live_denial_qualified"])
        self.assertFalse(verdict["exact_child_missing_handler_live_denial_qualified"])
        self.assertFalse(verdict["exact_parent_failed_handler_live_denial_qualified"])
        self.assertFalse(verdict["exact_child_failed_handler_live_denial_qualified"])
        self.assertFalse(verdict["same_uid_or_os_trust_qualified"])
        self.assertFalse(verdict["p4_qualified"])
        self.assertFalse(verdict["phase1_complete"])
        self.assertFalse(verdict["direct_write_qualified"])
        self.assertEqual(verdict["phase2_state"], "closed")
        self.assertEqual(verdict["phase3_state"], "closed")

        gates = {gate["id"]: gate for gate in self.status["phase1"]["gates"]}
        self.assertEqual(gates["P4"]["state"], "qualified")
        self.assertIn(RECEIPT.relative_to(ROOT).as_posix(), gates["P4"]["evidence"])


if __name__ == "__main__":
    unittest.main()
