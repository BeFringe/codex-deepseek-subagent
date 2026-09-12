from pathlib import Path
import hashlib
import json
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]
RECEIPT = (
    ROOT
    / "probes"
    / "current-signed-runtime-g4-explicit-plaintext-delivery-source-candidate.json"
)


class CurrentG4ExplicitPlaintextDeliveryCandidateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.receipt = json.loads(RECEIPT.read_text(encoding="utf-8"))
        cls.patches = [ROOT / entry["path"] for entry in cls.receipt["patch_chain"]]
        cls.patch_bytes = [path.read_bytes() for path in cls.patches]
        cls.incremental = cls.patch_bytes[1].decode("utf-8")

    def test_patch_chain_and_exact_source_are_hash_bound(self):
        self.assertEqual(
            self.receipt["source"]["base_commit"],
            "3d2ee51ca2d5db578f328aa75e20aa22c0197c9a",
        )
        for entry, payload in zip(self.receipt["patch_chain"], self.patch_bytes):
            self.assertEqual(hashlib.sha256(payload).hexdigest(), entry["sha256"])
        incremental = self.receipt["patch_chain"][1]
        self.assertEqual(len(self.patch_bytes[1]), incremental["bytes"])
        self.assertEqual(len(self.incremental.splitlines()), incremental["lines"])
        paths = re.findall(r"(?m)^diff --git a/(.+) b/(.+)$", self.incremental)
        self.assertEqual(len(paths), incremental["changed_paths"])
        self.assertTrue(all(left == right for left, right in paths))

    def test_plaintext_wire_is_explicit_and_legacy_safe(self):
        self.assertIn("plaintext_message_wire", self.incremental)
        self.assertIn("InterAgentCommunication::new_plaintext", self.incremental)
        self.assertIn("legacy agent-message projection", self.incremental)
        self.assertIn("has_delivery_metadata", self.incremental)
        self.assertIn("child_uses_plaintext_delivery", self.incremental)
        self.assertIn("AgentCommunicationKind::Result", self.incremental)
        behavior = self.receipt["behavior"]
        self.assertTrue(behavior["plaintext_projection_requires_explicit_durable_marker"])
        self.assertTrue(behavior["legacy_missing_marker_projects_as_agent_message"])
        self.assertTrue(behavior["completion_callback_uses_configured_delivery"])
        self.assertTrue(
            behavior["assignment_transport_wire_transport_request_normalization_remain_orthogonal"]
        )

    def test_rust_result_preserves_host_boundaries_without_promoting(self):
        validation = self.receipt["rust_validation"]
        self.assertEqual(validation["serial_core_suite"]["patch_regressions"], 0)
        self.assertEqual(
            validation["serial_core_suite"]["tests_run"],
            validation["serial_core_suite"]["passed"]
            + validation["serial_core_suite"]["failed"],
        )
        self.assertEqual(len(validation["serial_core_suite"]["host_test_boundaries"]), 2)
        self.assertFalse(validation["credential_values_recorded"])
        boundary = self.receipt["portable_boundary"]
        self.assertTrue(boundary["windows_rebuild_required"])
        self.assertTrue(boundary["windows_live_replay_required"])
        self.assertFalse(boundary["phase1_complete"])
        self.assertFalse(boundary["direct_write_qualified"])

    def test_incremental_patch_has_no_originating_host_path(self):
        self.assertIsNone(
            re.search(r"(?m)(?:^|[\"' (])/(?:Users|home)/[^/\s]+/", self.incremental)
        )
        self.assertNotIn("/private/tmp", self.incremental.lower())


if __name__ == "__main__":
    unittest.main()
