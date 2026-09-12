from __future__ import annotations

import hashlib
import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
RECEIPT = (
    ROOT
    / "probes"
    / "current-signed-runtime-plaintext-assignment-seam-source-candidate.json"
)
RUNTIME_INDEX = ROOT / "probes" / "codex-runtime-evidence-index.json"
STATUS = ROOT / "probes" / "phase1-g4-status.json"


class CurrentPlaintextAssignmentSourceCandidateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.receipt = json.loads(RECEIPT.read_text(encoding="utf-8"))
        artifact = self.receipt["source_patch"]
        self.patch_path = ROOT / artifact["path"]
        self.patch_bytes = self.patch_path.read_bytes()
        self.patch_text = self.patch_bytes.decode("utf-8")

    def test_receipt_binds_current_semantic_runtime_and_exact_patch(self) -> None:
        runtime_index = json.loads(RUNTIME_INDEX.read_text(encoding="utf-8"))
        current = runtime_index["runtime_roles"]["current_signed_runtime"]
        artifact = self.receipt["source_patch"]

        self.assertEqual(self.receipt["runtime_role"], "current_signed_runtime")
        self.assertEqual(self.receipt["codex_version"], current["codex_version"])
        self.assertEqual(self.receipt["base_source_commit"], current["source_commit"])
        self.assertEqual(hashlib.sha256(self.patch_bytes).hexdigest(), artifact["sha256"])
        self.assertEqual(len(self.patch_bytes), artifact["bytes"])
        self.assertEqual(len(self.patch_text.splitlines()), artifact["lines"])
        self.assertEqual(self.patch_text.count("diff --git "), artifact["changed_path_count"])
        self.assertEqual(len(self.receipt["changed_paths"]), artifact["changed_path_count"])
        self.assertTrue(all(path in self.patch_text for path in self.receipt["changed_paths"]))
        self.assertNotIn("Cargo.lock", self.patch_text)
        self.assertEqual(artifact["git_apply_check"], "pass")

    def test_candidate_is_explicit_opt_in_and_preserves_encrypted_default(self) -> None:
        interface = self.receipt["interface"]

        self.assertEqual(
            interface["config_key"], "features.multi_agent_v2.message_delivery"
        )
        self.assertEqual(interface["default"], "encrypted")
        self.assertEqual(interface["explicit_opt_in"], "plaintext")
        self.assertEqual(
            interface["operations"],
            ["spawn_agent", "send_message", "followup_task"],
        )
        for required in (
            "pub enum MultiAgentV2MessageDelivery",
            "message_delivery: MultiAgentV2MessageDelivery::Encrypted",
            "message_delivery: Option<MultiAgentV2MessageDelivery>",
            "config.multi_agent_v2.message_delivery = MultiAgentV2MessageDelivery::Plaintext",
            "plaintext_delivery_configured && self.encrypted_function_args.is_none()",
            ".is_some_and(Vec::is_empty)",
            "create_send_message_tool(self.encrypt_message)",
            "create_followup_task_tool(self.encrypt_message)",
            "ResponseItem::Message",
            'role: "user".to_string()',
            "plaintext_source_uses_user_message_wire_for_queue_and_trigger_modes",
        ):
            self.assertIn(required, self.patch_text)

    def test_candidate_does_not_expand_provider_or_mutation_authority(self) -> None:
        lowered = self.patch_text.lower()
        for forbidden in (
            "api_key",
            "api-key",
            "base_url",
            "base-url",
            "model_provider",
            "codex_cli_path",
            "/applications/codex.app",
        ):
            self.assertNotIn(forbidden, lowered)

        interface = self.receipt["interface"]
        self.assertTrue(interface["transport_only"])
        self.assertFalse(interface["grants_mutation_authority"])
        self.assertFalse(interface["changes_parent_provider_or_auth"])
        self.assertFalse(interface["uses_multi_agent_v1_fallback"])

    def test_source_success_is_not_promoted_to_live_qualification(self) -> None:
        source = self.receipt["source_results"]
        live = self.receipt["live_boundaries"]
        verdict = self.receipt["verdict"]

        self.assertTrue(source["candidate_compiles"])
        self.assertEqual(source["spawn_wire_matrix"], "5 passed")
        self.assertEqual(source["shared_queue_and_trigger_transport"], "2 passed")
        self.assertTrue(self.receipt["storage"]["cargo_target_deleted_after_tests"])
        self.assertFalse(self.receipt["storage"]["candidate_binary_built"])
        self.assertFalse(live["candidate_installed_or_selected"])
        self.assertFalse(live["gui_app_server_selected"])
        self.assertFalse(live["live_pretool_plaintext_observed"])
        self.assertFalse(live["live_subagentstart_capsule_consumption_observed"])
        self.assertTrue(verdict["source_candidate_qualified"])
        self.assertFalse(verdict["plaintext_assignment_seam_qualified"])
        self.assertFalse(verdict["phase1_complete"])
        self.assertFalse(verdict["direct_write_qualified"])

        status = json.loads(STATUS.read_text(encoding="utf-8"))["phase1"]
        self.assertFalse(status["declared_complete"])
        self.assertFalse(status["declared_direct_write_qualified"])


if __name__ == "__main__":
    unittest.main()
