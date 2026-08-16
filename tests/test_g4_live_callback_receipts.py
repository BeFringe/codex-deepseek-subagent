import json
from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]
RECORD = ROOT / "probes" / "g4-live-callback-receipts-20260817.json"
SHA256 = re.compile(r"^[0-9a-f]{64}$")


class G4LiveCallbackReceiptTests(unittest.TestCase):
    def test_live_record_is_exact_but_non_qualifying(self):
        record = json.loads(RECORD.read_text(encoding="utf-8"))

        self.assertEqual(record["schema"], 1)
        self.assertEqual(record["provider_free_tests"], {"count": 229, "status": "passed"})
        overlay = record["live_overlay"]
        self.assertEqual(overlay["v4_subagent_start_order"], 0)
        self.assertEqual(overlay["g4_subagent_start_order"], 1)
        self.assertEqual(overlay["invalid_lifecycle_additional_context_limits"], [])
        self.assertFalse(overlay["trust_hash_forged_or_copied"])
        self.assertFalse(overlay["fresh_process_trust_reapproval_proven"])

        callbacks = record["live_writer_callback_prefix"]
        self.assertEqual(callbacks["first_sequence"], 1)
        self.assertEqual(callbacks["last_sequence"], callbacks["event_count"])
        self.assertEqual(
            callbacks["authorized_pretooluse_count"],
            callbacks["observed_posttooluse_count"],
        )
        self.assertEqual(callbacks["pending_callback_count"], 0)
        self.assertFalse(callbacks["raw_payload_stored"])

        negative = record["failed_apply_patch_negative"]
        self.assertFalse(negative["disk_mutation_observed"])
        self.assertFalse(negative["posttooluse_callback_observed"])
        self.assertTrue(negative["later_overlapping_patch_denied"])
        abort = record["explicit_unchanged_abort"]
        self.assertEqual(
            abort["before_path_snapshot_sha256"],
            abort["after_path_snapshot_sha256"],
        )
        self.assertFalse(abort["recorded_as_posttooluse_callback"])
        self.assertEqual(abort["active_claims_after_abort"], 0)
        repeated = record["repeat_failed_patch_abort"]
        self.assertEqual(
            repeated["before_path_snapshot_sha256"],
            repeated["after_path_snapshot_sha256"],
        )
        self.assertEqual(repeated["verifier_status"], "aborted_unchanged")
        self.assertIsNone(repeated["verifier_posttooluse_sequence"])
        self.assertFalse(repeated["recorded_as_posttooluse_callback"])
        joined = record["post_abort_join_prefix"]
        self.assertEqual(joined["last_sequence"], joined["event_count"])
        self.assertEqual(joined["pending_callback_count"], 0)
        self.assertFalse(joined["raw_payload_stored"])

        qualification = record["qualification"]
        self.assertFalse(qualification["phase1_complete"])
        self.assertFalse(qualification["direct_write_qualified"])
        self.assertEqual(qualification["phase2"], "closed")
        self.assertEqual(qualification["phase3"], "closed")

        hashes = [
            overlay["hooks_json_sha256"],
            *overlay["installed_sha256"].values(),
            record["v4_preservation"]["plaintext_hook_sha256"],
            record["v4_preservation"]["agent_sha256"],
            callbacks["head_receipt_sha256"],
            callbacks["chain_sha256"],
            negative["claim_sha256"],
            abort["abort_sha256"],
            abort["before_path_snapshot_sha256"],
            abort["after_path_snapshot_sha256"],
            repeated["claim_sha256"],
            repeated["abort_sha256"],
            repeated["before_path_snapshot_sha256"],
            repeated["after_path_snapshot_sha256"],
            joined["chain_sha256"],
        ]
        self.assertTrue(all(SHA256.fullmatch(value) for value in hashes))


if __name__ == "__main__":
    unittest.main()
