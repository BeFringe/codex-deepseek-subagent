from pathlib import Path
import hashlib
import json
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]
RECEIPT = ROOT / "probes" / "p7-macos-current-candidate-writer-live-20260912.json"
SOURCE_RECEIPT = (
    ROOT
    / "probes"
    / "current-signed-runtime-g4-explicit-plaintext-delivery-source-candidate.json"
)


class P7MacOSCurrentCandidateLiveEvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.receipt = json.loads(RECEIPT.read_text(encoding="utf-8"))
        cls.source = json.loads(SOURCE_RECEIPT.read_text(encoding="utf-8"))

    def test_source_chain_is_exact_and_semantic(self):
        source = self.receipt["source"]
        self.assertEqual(source["base_commit"], self.source["source"]["base_commit"])
        self.assertEqual(
            source["semantic_version"], self.source["source"]["semantic_version"]
        )
        self.assertEqual(
            source["patch_sha256"], self.source["patch_chain"][-1]["sha256"]
        )
        self.assertEqual(
            source["cumulative_replay_sha256"],
            self.source["fresh_replay"]["canonical_cumulative_diff_sha256"],
        )
        self.assertEqual(
            hashlib.sha256(SOURCE_RECEIPT.read_bytes()).hexdigest(),
            source["patch_chain_receipt_sha256"],
        )
        self.assertEqual(
            source["candidate_sha256"],
            self.source["originating_host_build"]["codex_sha256"],
        )

    def test_historical_callback_negative_is_preserved_not_rewritten(self):
        historical = self.receipt["historical_unpromoted_negative"]
        self.assertEqual(historical["observed_boundary"], "parent final callback absent")
        self.assertFalse(historical["promoted"])
        self.assertTrue(historical["preserved"])
        self.assertNotEqual(
            historical["candidate_sha256"], self.receipt["source"]["candidate_sha256"]
        )

    def test_positive_negative_and_owner_close_the_macos_slice(self):
        negative = self.receipt["negative_calibration"]
        self.assertEqual(negative["pretool_decision"], "deny")
        self.assertEqual(negative["posttool_observation_count"], 0)
        self.assertEqual(negative["requested_foreign_path"], "foreign.txt")
        self.assertTrue(negative["disk_barriers_verified"])
        final = self.receipt["final_positive"]
        self.assertEqual(final["canonical_agent_path"], "/root/p7_macos_positive")
        self.assertEqual([item["path"] for item in final["changed_paths"]], ["qualified.txt"])
        self.assertTrue(final["callback_exact"])
        self.assertTrue(final["custom_tool_call_output_paired"])
        self.assertTrue(final["feasibility_bound_before_dispatch"])
        self.assertGreaterEqual(final["post_termination_barrier_interval_ns"], 2_000_000_000)
        self.assertTrue(final["authority_consumed"])
        self.assertTrue(final["exact_closed_writer_run_qualified"])

    def test_receipt_is_product_independent_and_does_not_overpromote(self):
        text = RECEIPT.read_text(encoding="utf-8")
        self.assertIsNone(re.search(r"/(?:Users|home|private/tmp)/", text))
        self.assertNotIn("LocalCAT", text)
        self.assertFalse(self.receipt["provider_boundary"]["credential_values_recorded"])
        regression = self.receipt["provider_free_regression"]
        self.assertEqual(
            regression["tests_run"], regression["passed"] + regression["skipped"]
        )
        self.assertEqual(regression["failed"], 0)
        decision = self.receipt["scope_decision"]
        self.assertTrue(decision["macos_exact_closed_writer_qualified"])
        self.assertEqual(decision["windows_current_candidate_state"], "pending")
        self.assertFalse(decision["p7_complete"])
        self.assertFalse(decision["phase1_complete"])
        self.assertFalse(decision["direct_write_qualified"])


if __name__ == "__main__":
    unittest.main()
