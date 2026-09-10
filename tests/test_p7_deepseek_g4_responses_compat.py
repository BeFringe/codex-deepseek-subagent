from __future__ import annotations

import hashlib
import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "probes" / "p7-live-deepseek-g4-responses-compat-20260910.json"


class P7DeepSeekG4ResponsesCompatibilityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.evidence = json.loads(EVIDENCE.read_text(encoding="utf-8"))

    def test_positive_run_binds_portable_source_patch(self) -> None:
        runtime = self.evidence["runtime"]
        patch = ROOT / runtime["cumulative_source_patch"]

        self.assertEqual(
            hashlib.sha256(patch.read_bytes()).hexdigest(),
            runtime["cumulative_source_patch_sha256"],
        )
        self.assertEqual(runtime["codex_semantic_version"], "0.153.4")
        self.assertFalse(runtime["gui_app_server_selected"])

    def test_controls_distinguish_namespace_and_pairing(self) -> None:
        namespaced, flat = self.evidence["negative_controls"]

        self.assertEqual(namespaced["tool_namespace"], "g4_assignment")
        self.assertIsNone(flat["tool_namespace"])
        self.assertTrue(namespaced["matching_local_output"])
        self.assertTrue(flat["matching_local_output"])
        self.assertEqual(
            flat["intervening_rollout_item"],
            "hooks.additional_context developer message",
        )

        contract = self.evidence["provider_contract"]
        self.assertFalse(contract["provider_namespace_tools_enabled"])
        self.assertTrue(contract["provider_requires_function_call_output_adjacency"])
        self.assertEqual(contract["assignment_transport"], "plaintext SubagentStart Hook")
        self.assertEqual(contract["wire_transport"], "responses-direct")

    def test_live_result_is_narrow_and_fail_closed(self) -> None:
        positive = self.evidence["positive_run"]
        self.assertEqual(positive["tool_call"]["count"], 1)
        self.assertEqual(positive["tool_call"]["matching_output_count"], 1)
        self.assertEqual(positive["tool_call"]["arguments"], "{}")
        self.assertIsNone(positive["tool_call"]["namespace"])
        self.assertFalse(positive["provider_missing_tool_output_error"])
        self.assertTrue(positive["final_attestation_accepted"])
        self.assertEqual(positive["compatibility_state"]["active_count"], 0)
        self.assertEqual(positive["compatibility_state"]["reported_count"], 1)
        self.assertEqual(positive["compatibility_state"]["unresolved_count"], 0)
        self.assertTrue(positive["close_receipt"]["post_close_child_absent"])
        self.assertFalse(positive["close_receipt"]["process_tree_quiescence_claimed"])
        self.assertEqual(positive["git_status_short"], "")
        self.assertTrue(positive["two_post_exit_barriers_equal"])

        verdict = self.evidence["verdict"]
        self.assertTrue(verdict["macos_deepseek_g4_tool_loop_qualified"])
        self.assertFalse(verdict["strong_process_tree_quiescence_observed"])
        self.assertTrue(verdict["windows_same_patch_parity_pending"])
        self.assertFalse(verdict["phase1_complete"])
        self.assertFalse(verdict["direct_write_qualified"])

    def test_evidence_contains_no_credential_values(self) -> None:
        boundary = self.evidence["credential_boundary"]
        self.assertFalse(boundary["chatgpt_auth_value_read"])
        self.assertTrue(boundary["deepseek_credential_present"])
        self.assertFalse(boundary["deepseek_credential_value_recorded"])
        self.assertFalse(boundary["credential_value_committed"])
        self.assertNotIn("experimental_bearer_token", EVIDENCE.read_text(encoding="utf-8"))

    def test_originating_manifest_hash_when_available(self) -> None:
        positive = self.evidence["positive_run"]
        manifest = Path(positive["manifest_path"])
        if not manifest.is_file():
            self.skipTest("originating-host manifest is unavailable")
        self.assertEqual(
            hashlib.sha256(manifest.read_bytes()).hexdigest(),
            positive["manifest_sha256"],
        )


if __name__ == "__main__":
    unittest.main()
