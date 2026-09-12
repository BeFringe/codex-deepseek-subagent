from pathlib import Path
import hashlib
import json
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]
RECEIPT = (
    ROOT
    / "probes"
    / "current-signed-runtime-g4-explicit-plaintext-delivery-rust-validation-20260912.json"
)


class CurrentG4ExplicitPlaintextDeliveryRustValidationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.receipt = json.loads(RECEIPT.read_text(encoding="utf-8"))
        cls.source_receipt_path = ROOT / cls.receipt["source_chain_receipt"]
        cls.source_receipt = json.loads(
            cls.source_receipt_path.read_text(encoding="utf-8")
        )

    def test_validation_binds_the_immutable_live_source_chain(self):
        self.assertEqual(
            hashlib.sha256(self.source_receipt_path.read_bytes()).hexdigest(),
            self.receipt["source_chain_receipt_sha256"],
        )
        source = self.receipt["source"]
        self.assertEqual(source["base_commit"], self.source_receipt["source"]["base_commit"])
        self.assertEqual(
            source["semantic_version"], self.source_receipt["source"]["semantic_version"]
        )
        self.assertEqual(
            source["patch_sha256"], self.source_receipt["patch_chain"][-1]["sha256"]
        )
        self.assertEqual(
            source["candidate_sha256"],
            self.source_receipt["originating_host_build"]["codex_sha256"],
        )

    def test_serial_result_preserves_each_nonpass_and_isolates_it(self):
        serial = self.receipt["current_source_serial_core"]
        self.assertEqual(serial["tests_run"], serial["passed"] + serial["failed"])
        self.assertEqual(serial["failed"], 3)
        self.assertEqual(serial["patch_regressions"], 0)
        by_name = {item["name"]: item for item in serial["failed_tests"]}
        self.assertEqual(len(by_name), 3)
        self.assertEqual(
            by_name[
                "session::turn::tests::post_sampling_token_estimate_is_disabled_by_always_on_sinks"
            ]["isolated_current_source"],
            "passed",
        )
        for name in (
            "session::tests::managed_network_proxy_decider_survives_full_access_start",
            "session::tests::user_shell_commands_do_not_inherit_managed_network_proxy",
        ):
            self.assertEqual(by_name[name]["upstream_source_comparison"], "failed_same")

    def test_targeted_callback_and_legacy_boundaries_all_passed(self):
        targeted = self.receipt["targeted_current_source"]
        self.assertTrue(targeted["all_passed"])
        self.assertIn(
            "multi_agent_v2_completion_queues_message_for_direct_parent",
            targeted["tests"],
        )
        self.assertIn(
            "fork_turn_positions_use_plaintext_messages_and_delivery_metadata",
            targeted["tests"],
        )

    def test_host_boundaries_do_not_promote_phase_or_leak_paths(self):
        text = RECEIPT.read_text(encoding="utf-8")
        self.assertIsNone(re.search(r"/(?:Users|home|private/tmp)/", text))
        decision = self.receipt["decision"]
        self.assertFalse(decision["callback_patch_regression_observed"])
        self.assertFalse(decision["host_boundaries_promoted_as_phase1_evidence"])
        self.assertFalse(decision["phase1_complete"])
        self.assertFalse(decision["direct_write_qualified"])
        self.assertFalse(
            self.receipt["upstream_source_comparison"]["credential_values_recorded"]
        )


if __name__ == "__main__":
    unittest.main()
