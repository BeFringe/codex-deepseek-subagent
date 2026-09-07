import hashlib
import json
import pathlib
import re
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
RECEIPT = ROOT / "probes" / "current-signed-runtime-plaintext-child-provider-seam-source-candidate.json"
RUNTIME_INDEX = ROOT / "probes" / "codex-runtime-evidence-index.json"
SHA256 = re.compile(r"[0-9a-f]{64}")


class CurrentChildProviderSeamSourceCandidateTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.receipt = json.loads(RECEIPT.read_text())
        cls.runtime_index = json.loads(RUNTIME_INDEX.read_text())
        cls.patch_path = ROOT / cls.receipt["source_patch"]["path"]
        cls.patch_bytes = cls.patch_path.read_bytes()
        cls.patch_text = cls.patch_bytes.decode("utf-8")

    def test_receipt_tracks_current_runtime_semantically(self) -> None:
        runtime_role = self.runtime_index["current_runtime_role"]
        runtime = self.runtime_index["runtime_roles"][runtime_role]
        self.assertEqual(self.receipt["runtime_role"], runtime_role)
        self.assertEqual(self.receipt["base_source_commit"], runtime["source_commit"])
        self.assertEqual(
            self.receipt["headless_binary"]["reported_version"],
            runtime["codex_version"],
        )

    def test_patch_is_exact_and_cargo_lock_free(self) -> None:
        artifact = self.receipt["source_patch"]
        self.assertRegex(artifact["sha256"], SHA256)
        self.assertEqual(hashlib.sha256(self.patch_bytes).hexdigest(), artifact["sha256"])
        self.assertEqual(len(self.patch_bytes), artifact["bytes"])
        self.assertEqual(len(self.patch_text.splitlines()), artifact["lines"])
        self.assertEqual(self.patch_text.count("diff --git "), artifact["changed_path_count"])
        self.assertNotIn("Cargo.lock", self.patch_text)
        self.assertFalse(artifact["cargo_lock_included"])

    def test_provider_choice_is_an_exact_parent_allowlist_not_a_role_boolean(self) -> None:
        seam = self.receipt["provider_authority_seam"]
        self.assertEqual(
            seam["config_key"], "features.multi_agent_v2.child_model_providers"
        )
        self.assertIn("child_model_providers", self.patch_text)
        self.assertIn("get(role_name)", self.patch_text)
        self.assertFalse(seam["role_file_can_self_authorize_provider"])
        self.assertEqual(seam["unknown_authorized_provider"], "deny")
        self.assertEqual(seam["cross_provider_requires_openai_auth"], "deny")
        self.assertEqual(seam["resume_stored_provider_mismatch"], "deny")

    def test_seam_does_not_expand_parent_or_mutation_authority(self) -> None:
        seam = self.receipt["provider_authority_seam"]
        self.assertFalse(seam["changes_parent_provider"])
        self.assertFalse(seam["changes_assignment_transport"])
        self.assertFalse(seam["grants_mutation_authority"])
        self.assertFalse(seam["credential_values_read_or_stored"])
        self.assertIn(
            "authorized child model provider cannot require inherited OpenAI auth",
            self.patch_text,
        )

    def test_unknown_model_tools_require_exact_role_and_applied_provider(self) -> None:
        seam = self.receipt["provider_authority_seam"]
        self.assertIn("exact child role", seam["unknown_model_v2_tool_projection"])
        self.assertEqual(seam["wrong_role_or_applied_provider"], "deny")
        self.assertIn(
            "exact_child_provider_mapping_authorizes_v2_tools",
            self.patch_text,
        )
        self.assertIn(
            "child_provider_mapping_must_match_exact_role_and_applied_provider",
            self.patch_text,
        )

    def test_live_qualification_remains_closed(self) -> None:
        live = self.receipt["live_boundaries"]
        verdict = self.receipt["verdict"]
        self.assertFalse(live["candidate_installed_or_selected"])
        self.assertFalse(live["gui_app_server_selected"])
        self.assertFalse(live["live_config_modified"])
        self.assertTrue(live["native_zhipu_child_observed"])
        self.assertTrue(live["native_zhipu_list_agents_call_observed"])
        self.assertTrue(live["subagentstop_parent_callback_observed"])
        self.assertTrue(verdict["native_external_child_readonly_tool_loop_qualified"])
        self.assertFalse(verdict["native_external_child_qualified"])
        self.assertFalse(verdict["phase1_complete"])
        self.assertFalse(verdict["direct_write_qualified"])
        self.assertEqual(verdict["phase2_state"], "closed")
        self.assertEqual(verdict["phase3_state"], "closed")

    def test_build_cache_was_removed_but_candidate_was_preserved(self) -> None:
        storage = self.receipt["storage"]
        self.assertTrue(storage["cargo_target_deleted_after_validation"])
        self.assertFalse(storage["cleanup_pending"])
        self.assertTrue(storage["candidate_binary_preserved"])


if __name__ == "__main__":
    unittest.main()
