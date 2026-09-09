from __future__ import annotations

import json
from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]
RECEIPT = (
    ROOT
    / "probes"
    / "g4-current-app-failed-patch-callback-regression-20260909.json"
)
STATUS = ROOT / "probes" / "phase1-g4-status.json"
SHA256 = re.compile(r"^[0-9a-f]{64}$")
GIT_OBJECT_ID = re.compile(r"^[0-9a-f]{40}$")


class G4CurrentAppFailedPatchCallbackRegressionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.receipt = json.loads(RECEIPT.read_text(encoding="utf-8"))
        cls.status = json.loads(STATUS.read_text(encoding="utf-8"))

    def test_exact_installed_app_and_root_identity_are_frozen(self) -> None:
        runtime = self.receipt["runtime"]
        actor = self.receipt["actor"]
        git = self.receipt["git"]

        self.assertEqual(runtime["surface"], "installed_codex_desktop_app_server")
        self.assertEqual(runtime["codex_cli_semver"], "0.153.4")
        self.assertRegex(runtime["binary_sha256"], SHA256)
        self.assertFalse(runtime["gui_app_server_replaced"])
        self.assertFalse(runtime["credential_value_observed"])
        self.assertEqual(actor["thread_id"], actor["runtime_session_id"])
        self.assertEqual(actor["canonical_agent_path"], "/root")
        self.assertEqual(git["branch"], "main")
        self.assertRegex(git["full_head"], GIT_OBJECT_ID)
        self.assertFalse(git["index_changed"])

    def test_handler_failure_has_pretooluse_but_no_same_id_posttooluse(self) -> None:
        trigger = self.receipt["trigger"]
        claim = self.receipt["writer_claim"]

        self.assertEqual(trigger["tool_name"], "apply_patch")
        self.assertEqual(trigger["pretooluse_stage"], "authorized")
        self.assertRegex(trigger["pretooluse_receipt_sha256"], SHA256)
        self.assertFalse(trigger["posttooluse_callback_observed"])
        self.assertFalse(trigger["target_bytes_changed"])
        self.assertFalse(trigger["multi_agent_competition_involved"])
        self.assertFalse(trigger["child_writer_involved"])
        self.assertTrue(claim["persisted_after_handler_failure"])
        self.assertTrue(claim["blocked_following_overlapping_patch"])
        self.assertTrue(claim["absent_after_exact_recovery"])

    def test_recovery_is_unchanged_and_candidate_fix_is_not_overclaimed(self) -> None:
        recovery = self.receipt["exact_recovery"]
        comparison = self.receipt["comparison"]
        verdict = self.receipt["scope_verdict"]

        self.assertEqual(
            recovery["classification"],
            "aborted_unchanged_after_missing_callback",
        )
        self.assertEqual(
            recovery["before_path_snapshot_sha256"],
            recovery["after_path_snapshot_sha256"],
        )
        self.assertEqual(
            recovery["before_snapshot_sha256"],
            recovery["after_snapshot_sha256"],
        )
        for key in ("abort_sha256", "abort_file_sha256"):
            self.assertRegex(recovery[key], SHA256)
        self.assertFalse(recovery["raw_payload_stored"])
        self.assertTrue(comparison["headless_candidate_emitted_same_id_posttooluse"])
        self.assertFalse(comparison["installed_app_emitted_same_id_posttooluse"])
        self.assertTrue(
            comparison["installed_app_still_needs_fix_or_equivalent_reconciliation"]
        )
        self.assertTrue(verdict["single_parent_handler_failure_callback_gap"])
        self.assertFalse(verdict["shared_worktree_writer_race"])
        self.assertTrue(verdict["lease_failed_closed_until_exact_recovery"])
        self.assertFalse(verdict["automatic_failed_tool_callback_complete"])
        self.assertFalse(verdict["p5b_complete"])
        self.assertFalse(verdict["p7_complete"])
        self.assertFalse(verdict["phase1_complete"])
        self.assertFalse(verdict["direct_write_qualified"])

    def test_status_assigns_installed_callback_regression_to_p7(self) -> None:
        gates = {gate["id"]: gate for gate in self.status["phase1"]["gates"]}
        rel = "probes/g4-current-app-failed-patch-callback-regression-20260909.json"
        test_rel = "tests/test_g4_current_app_failed_patch_callback_regression.py"

        for gate_id in ("P5b", "P7"):
            gate = gates[gate_id]
            self.assertIn(rel, gate["evidence"])
            self.assertIn(test_rel, gate["evidence"])
        self.assertEqual(gates["P5b"]["state"], "qualified")
        self.assertEqual(gates["P7"]["state"], "partial")
        self.assertIn("PostToolUse", gates["P7"]["blocker"])
        self.assertIn("installed 0.153.4", gates["P7"]["blocker"])


if __name__ == "__main__":
    unittest.main()
