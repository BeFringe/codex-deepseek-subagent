from pathlib import Path
import hashlib
import json
import unittest


ROOT = Path(__file__).resolve().parents[1]
RECEIPT = (
    ROOT
    / "probes"
    / "current-signed-runtime-g4-complete-source-rust-validation-20260912.json"
)
SOURCE = (
    ROOT
    / "probes"
    / "current-signed-runtime-g4-complete-source-tree-20260912.json"
)


class CurrentG4CompleteSourceRustValidationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.receipt = json.loads(RECEIPT.read_text(encoding="utf-8"))
        cls.source = json.loads(SOURCE.read_text(encoding="utf-8"))

    def test_validation_binds_the_complete_tree_and_candidate(self):
        source = self.receipt["source"]
        reconstruction = self.source["complete_reconstruction"]
        self.assertEqual(
            hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
            self.receipt["complete_source_receipt_sha256"],
        )
        self.assertEqual(source["complete_tree"], reconstruction["tree"])
        self.assertEqual(
            source["complete_replay_sha256"],
            reconstruction["binary_full_index_diff_sha256"],
        )
        self.assertEqual(
            source["complete_source_receipt_sha256"],
            self.receipt["complete_source_receipt_sha256"],
        )
        self.assertEqual(
            source["candidate_sha256"],
            self.receipt["cold_build"]["candidate_sha256"],
        )
        self.assertTrue(self.receipt["cold_build"]["single_source_root"])
        self.assertTrue(
            self.receipt["cold_build"]["shared_cross_worktree_target_rejected"]
        )

    def test_targeted_and_serial_results_are_not_overstated(self):
        targeted = self.receipt["targeted_current_source"]
        self.assertTrue(targeted["all_passed"])
        self.assertEqual(targeted["tests_run"], len(targeted["tests"]))
        self.assertEqual(targeted["tests_run"], 9)

        serial = self.receipt["current_source_serial_core"]
        self.assertEqual(serial["tests_run"], 2470)
        self.assertEqual(serial["passed"] + serial["failed"], serial["tests_run"])
        self.assertEqual(serial["patch_regressions"], 0)
        self.assertEqual(len(serial["failed_tests"]), serial["failed"])
        self.assertEqual(
            {item["classification"] for item in serial["failed_tests"]},
            {
                "originating_host_network_baseline",
                "originating_host_proxy_injection",
                "serial_process_global_tracing_order",
            },
        )

    def test_validation_does_not_promote_host_boundaries_or_phase(self):
        decision = self.receipt["decision"]
        self.assertTrue(decision["complete_source_and_candidate_bound"])
        self.assertFalse(decision["callback_patch_regression_observed"])
        self.assertFalse(decision["host_boundaries_promoted_as_phase1_evidence"])
        self.assertTrue(decision["windows_replay_required"])
        self.assertFalse(decision["phase1_complete"])
        self.assertFalse(decision["direct_write_qualified"])
        self.assertEqual(decision["phase2_state"], "closed")
        self.assertEqual(decision["phase3_state"], "closed")
        self.assertFalse(self.receipt["credential_values_recorded"])


if __name__ == "__main__":
    unittest.main()
