from __future__ import annotations

import hashlib
import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
RECEIPT = ROOT / "probes" / "codex-0.148.0-alpha.9-plaintext-assignment-seam-candidate.json"
STATUS = ROOT / "probes" / "phase1-g4-status.json"


class NativePlaintextSeamSourceCandidateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.receipt = json.loads(RECEIPT.read_text(encoding="utf-8"))
        artifact = self.receipt["artifact"]
        self.patch_path = ROOT / artifact["path"]
        self.patch_bytes = self.patch_path.read_bytes()
        self.patch_text = self.patch_bytes.decode("utf-8")

    def test_patch_is_exactly_bound_to_receipt(self) -> None:
        artifact = self.receipt["artifact"]
        self.assertEqual(
            hashlib.sha256(self.patch_bytes).hexdigest(), artifact["sha256"]
        )
        self.assertEqual(len(self.patch_bytes), artifact["bytes"])
        self.assertEqual(len(self.patch_text.splitlines()), artifact["lines"])
        self.assertEqual(self.patch_text.count("diff --git "), 12)
        self.assertNotIn("Cargo.lock", self.patch_text)

    def test_candidate_is_explicit_opt_in_and_defaults_encrypted(self) -> None:
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
            "message_delivery: Option<MultiAgentV2MessageDelivery>",
            "message_delivery: MultiAgentV2MessageDelivery::Encrypted",
            "config.multi_agent_v2.message_delivery = MultiAgentV2MessageDelivery::Plaintext",
            "create_send_message_tool(self.encrypt_message)",
            "create_followup_task_tool(self.encrypt_message)",
            "encrypt_message: encrypt_messages",
        ):
            self.assertIn(required, self.patch_text)

    def test_candidate_does_not_change_provider_or_credential_configuration(self) -> None:
        lowered = self.patch_text.lower()
        for forbidden in ("api_key", "api-key", "base_url", "base-url"):
            self.assertNotIn(forbidden, lowered)
        interface = self.receipt["interface"]
        self.assertFalse(interface["changes_parent_provider_or_auth"])
        self.assertFalse(interface["uses_multi_agent_v1_fallback"])
        self.assertTrue(interface["transport_only"])
        self.assertFalse(interface["grants_mutation_authority"])

    def test_release_binary_is_frozen_but_not_live_selected(self) -> None:
        build = self.receipt["binary_build"]
        self.assertEqual(build["exit_code"], 0)
        self.assertEqual(
            build["sha256"],
            "e2874bda15552fac7b677b2553978a452c8c7beb5cae536ec95aead4d8b174d6",
        )
        self.assertEqual(build["bytes"], 293620392)
        self.assertEqual(build["version_output"], "codex-cli 0.148.0-alpha.9")
        self.assertIn("arm64", build["format"])
        self.assertIn("ad-hoc", build["signature"])
        self.assertFalse(build["installed_or_selected_live"])

    def test_source_success_is_not_promoted_to_live_qualification(self) -> None:
        source = self.receipt["source_result"]
        verdict = self.receipt["verdict"]
        self.assertTrue(source["candidate_compiles"])
        self.assertTrue(source["default_encrypted_schema_preserved"])
        self.assertTrue(source["explicit_plaintext_schema_available"])
        self.assertFalse(source["live_encrypted_function_args_empty_array_observed"])
        self.assertFalse(source["live_pretool_plaintext_observed"])
        self.assertFalse(source["live_delivered_plaintext_equality_observed"])
        self.assertFalse(verdict["live_candidate_installed"])
        self.assertFalse(verdict["plaintext_assignment_seam_qualified"])
        self.assertFalse(verdict["phase1_complete"])
        self.assertFalse(verdict["direct_write_qualified"])
        self.assertFalse(verdict["phase2_open"])
        self.assertFalse(verdict["phase3_open"])

        status = json.loads(STATUS.read_text(encoding="utf-8"))["phase1"]
        self.assertTrue(status["declared_complete"])
        self.assertTrue(status["declared_direct_write_qualified"])


if __name__ == "__main__":
    unittest.main()
