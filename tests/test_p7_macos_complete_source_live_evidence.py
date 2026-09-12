from pathlib import Path
import hashlib
import json
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]
RECEIPT = ROOT / "probes" / "p7-macos-complete-source-writer-live-20260912.json"
COMPLETE_SOURCE = (
    ROOT
    / "probes"
    / "current-signed-runtime-g4-complete-source-tree-20260912.json"
)
RUST = (
    ROOT
    / "probes"
    / "current-signed-runtime-g4-complete-source-rust-validation-20260912.json"
)
SUPERSEDED = ROOT / "probes" / "p7-macos-current-candidate-writer-live-20260912.json"


class P7MacOSCompleteSourceLiveEvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.receipt = json.loads(RECEIPT.read_text(encoding="utf-8"))
        cls.complete = json.loads(COMPLETE_SOURCE.read_text(encoding="utf-8"))
        cls.rust = json.loads(RUST.read_text(encoding="utf-8"))

    def test_source_tree_candidate_and_receipts_are_exact(self):
        source = self.receipt["source"]
        reconstruction = self.complete["complete_reconstruction"]
        self.assertEqual(source["base_commit"], self.complete["source"]["base_commit"])
        self.assertEqual(source["complete_tree"], reconstruction["tree"])
        self.assertEqual(
            source["complete_replay_sha256"],
            reconstruction["binary_full_index_diff_sha256"],
        )
        self.assertEqual(
            source["complete_source_receipt_sha256"],
            hashlib.sha256(COMPLETE_SOURCE.read_bytes()).hexdigest(),
        )
        self.assertEqual(source["candidate_sha256"], self.rust["source"]["candidate_sha256"])

    def test_incomplete_prior_binding_is_preserved_but_cannot_promote(self):
        superseded = self.receipt["superseded_incomplete_source_binding"]
        self.assertEqual(
            superseded["receipt_sha256"],
            hashlib.sha256(SUPERSEDED.read_bytes()).hexdigest(),
        )
        self.assertFalse(superseded["complete_source_tree_bound"])
        self.assertFalse(superseded["promoted"])
        self.assertTrue(superseded["preserved"])
        self.assertNotEqual(
            superseded["candidate_sha256"], self.receipt["source"]["candidate_sha256"]
        )

    def test_negative_and_final_positive_close_the_exact_writer_slice(self):
        negative = self.receipt["negative_calibration"]
        self.assertEqual(negative["pretool_decision"], "deny")
        self.assertEqual(negative["posttool_observation_count"], 0)
        self.assertTrue(negative["disk_barriers_verified"])
        self.assertTrue(negative["child_absent_after_close"])

        final = self.receipt["final_positive"]
        self.assertEqual(final["canonical_agent_path"], "/root/p7_macos_positive")
        self.assertEqual([item["path"] for item in final["changed_paths"]], ["qualified.txt"])
        self.assertTrue(final["callback_exact"])
        self.assertTrue(final["custom_tool_call_output_paired"])
        self.assertTrue(final["feasibility_bound_before_dispatch"])
        self.assertGreaterEqual(final["post_termination_barrier_interval_ns"], 2_000_000_000)
        self.assertTrue(final["in_flight_authority_empty"])
        self.assertTrue(final["authority_consumed"])
        self.assertTrue(final["exact_closed_writer_run_qualified"])

    def test_receipt_is_product_independent_and_fail_closed(self):
        text = RECEIPT.read_text(encoding="utf-8")
        self.assertIsNone(re.search(r"(?:[A-Za-z]:\\|/(?:Users|home|private/tmp)/)", text))
        self.assertNotIn("LocalCAT", text)
        self.assertFalse(self.receipt["provider_boundary"]["credential_values_recorded"])
        regression = self.receipt["provider_free_regression"]
        self.assertEqual(
            regression["tests_run"], regression["passed"] + regression["skipped"]
        )
        self.assertEqual(regression["failed"], 0)
        self.assertTrue(regression["agent_template_checks_passed"])
        decision = self.receipt["scope_decision"]
        self.assertTrue(decision["macos_exact_closed_writer_qualified"])
        self.assertEqual(decision["windows_current_candidate_state"], "pending")
        self.assertFalse(decision["p7_complete"])
        self.assertFalse(decision["phase1_complete"])
        self.assertFalse(decision["direct_write_qualified"])


if __name__ == "__main__":
    unittest.main()
