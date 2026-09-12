from __future__ import annotations

import json
from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]
RECEIPT_PATH = ROOT / "probes" / "g4-live-missing-posttooluse-recovery-20260907.json"
SHA256 = re.compile(r"^[0-9a-f]{64}$")


class G4LiveMissingPostToolUseRecoveryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.receipt = json.loads(RECEIPT_PATH.read_text(encoding="utf-8"))

    def test_failed_patch_claim_is_bound_to_exact_root_and_paths(self) -> None:
        trigger = self.receipt["trigger"]
        actor = self.receipt["actor"]

        self.assertEqual(actor["agent_type"], "root")
        self.assertEqual(actor["canonical_agent_path"], "/root")
        self.assertEqual(trigger["tool_name"], "apply_patch")
        self.assertEqual(len(trigger["paths"]), 2)
        self.assertEqual(trigger["failure_stage"], "apply_patch_context_verification")
        self.assertFalse(trigger["posttooluse_callback_observed"])
        self.assertFalse(trigger["target_bytes_changed"])
        self.assertTrue(self.receipt["claim"]["blocked_next_overlapping_patch"])

    def test_recovery_requires_exact_identity_and_unchanged_path_snapshot(self) -> None:
        claim = self.receipt["claim"]
        recovery = self.receipt["recovery"]

        self.assertRegex(claim["claim_sha256"], SHA256)
        self.assertTrue(claim["absent_after_recovery"])
        self.assertTrue(recovery["first_noncanonical_root_agent_type_attempt_denied"])
        self.assertTrue(recovery["exact_sessionmeta_root_identity_required"])
        self.assertEqual(
            recovery["classification"],
            "aborted_unchanged_after_missing_callback",
        )
        self.assertEqual(
            recovery["before_path_snapshot_sha256"],
            recovery["after_path_snapshot_sha256"],
        )
        self.assertRegex(recovery["abort_sha256"], SHA256)
        self.assertRegex(recovery["abort_envelope_sha256"], SHA256)
        self.assertTrue(recovery["abort_present_after_recovery"])
        self.assertFalse(recovery["raw_payload_stored"])

    def test_real_recovery_does_not_overclaim_writer_or_phase_qualification(self) -> None:
        verdict = self.receipt["scope_verdict"]

        self.assertFalse(verdict["multi_agent_competition_involved"])
        self.assertFalse(verdict["child_writer_involved"])
        self.assertTrue(verdict["multi_file_patch_context_mismatch_triggered"])
        self.assertTrue(verdict["lease_fail_closed_after_missing_callback"])
        self.assertTrue(verdict["unchanged_recovery_reproducible"])
        self.assertFalse(verdict["automatic_failed_tool_callback_complete"])
        self.assertFalse(verdict["all_surface_writer_serialization_qualified"])
        self.assertFalse(verdict["p5b_complete"])
        self.assertFalse(verdict["phase1_complete"])
        self.assertFalse(verdict["direct_write_qualified"])


if __name__ == "__main__":
    unittest.main()
