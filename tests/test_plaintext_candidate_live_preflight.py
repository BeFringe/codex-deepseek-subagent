from pathlib import Path
import json
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]
RECEIPT = (
    ROOT
    / "probes"
    / "codex-0.148.0-alpha.9-plaintext-live-selection-preflight.json"
)
SOURCE_RECEIPT = (
    ROOT
    / "probes"
    / "codex-0.148.0-alpha.9-plaintext-assignment-seam-candidate.json"
)
INCIDENT_RECEIPT = ROOT / "probes" / "g4-candidate-live-selection-incident-20260817.json"
SHA256 = re.compile(r"^[0-9a-f]{64}$")


class PlaintextCandidateLivePreflightTests(unittest.TestCase):
    def setUp(self):
        self.receipt = json.loads(RECEIPT.read_text(encoding="utf-8"))
        self.source_receipt = json.loads(SOURCE_RECEIPT.read_text(encoding="utf-8"))
        self.incident_receipt = json.loads(INCIDENT_RECEIPT.read_text(encoding="utf-8"))

    def test_preflight_binds_candidate_app_and_selection_seam(self):
        receipt = self.receipt
        candidate = receipt["candidate"]
        baseline = receipt["current_app_baseline"]
        selection = receipt["selection_seam"]

        self.assertEqual(receipt["schema"], 1)
        self.assertEqual(
            candidate["source_commit"], self.source_receipt["codex"]["source_commit"]
        )
        self.assertEqual(
            candidate["patch_sha256"], self.source_receipt["artifact"]["sha256"]
        )
        self.assertEqual(
            candidate["release_binary_sha256"],
            self.source_receipt["binary_build"]["sha256"],
        )
        self.assertEqual(
            candidate["release_binary_bytes"],
            self.source_receipt["binary_build"]["bytes"],
        )
        self.assertTrue(candidate["release_binary_path"].startswith("/"))
        self.assertTrue(SHA256.fullmatch(candidate["release_binary_sha256"]))
        self.assertTrue(SHA256.fullmatch(baseline["resource_binary_sha256"]))
        self.assertTrue(baseline["resource_binary_signature_valid"])
        self.assertTrue(baseline["bundle_deep_strict_signature_valid"])
        self.assertEqual(selection["mechanism"], "CODEX_CLI_PATH")
        self.assertEqual(selection["codex_cli_path_anchor_count"], 4)
        self.assertFalse(selection["signed_app_resource_replacement_required"])
        self.assertFalse(selection["live_config_edit_required"])
        self.assertTrue(selection["app_restart_required"])

    def test_historical_wrapper_hash_is_superseded_by_the_incident_guard(self):
        selection = self.receipt["selection_seam"]
        incident = self.incident_receipt
        hardened = incident["hardened_wrapper"]
        wrapper = ROOT / hardened["path"]
        self.assertTrue(SHA256.fullmatch(hardened["sha256"]))
        self.assertEqual(
            selection["wrapper_sha256"],
            incident["historical_selection"]["historical_wrapper_sha256"],
        )
        self.assertNotEqual(selection["wrapper_sha256"], hardened["sha256"])
        self.assertEqual(
            selection["wrapper_injected_config"],
            [
                "features.multi_agent_v2.enabled=true",
                "features.multi_agent_v2.message_delivery=plaintext",
            ],
        )
        source = wrapper.read_text(encoding="utf-8")
        self.assertIn("CODEX_G4_CANDIDATE_SHA256", source)
        self.assertIn("GUI and server entry points are forbidden", source)
        self.assertNotIn("provider", source.lower())
        self.assertNotIn("base_url", source.lower())

    def test_operational_marker_is_not_authority(self):
        guard = self.receipt["operational_guard"]
        self.assertTrue(guard["prevents_accidental_wrapper_execution"])
        self.assertFalse(guard["is_trusted_user_consent_signal"])
        self.assertFalse(guard["grants_mutation_authority"])
        self.assertFalse(guard["qualifies_direct_write"])

    def test_preflight_does_not_claim_live_or_rollback_completion(self):
        receipt = self.receipt
        verdict = receipt["verdict"]
        self.assertFalse(receipt["candidate"]["selected_live"])
        self.assertFalse(receipt["authorization"]["live_candidate_selection_authorized"])
        self.assertTrue(
            receipt["authorization"]["next_live_step_requires_explicit_user_approval"]
        )
        self.assertFalse(receipt["rollback_plan"]["performed"])
        self.assertFalse(receipt["rollback_plan"]["qualifies_exit_receipt"])
        self.assertFalse(verdict["live_plaintext_receipt_present"])
        self.assertFalse(verdict["phase1_complete"])
        self.assertFalse(verdict["direct_write_qualified"])
        self.assertFalse(verdict["phase2_open"])
        self.assertFalse(verdict["phase3_open"])


if __name__ == "__main__":
    unittest.main()
