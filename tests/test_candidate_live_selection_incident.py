from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]
INCIDENT = ROOT / "probes" / "g4-candidate-live-selection-incident-20260817.json"
ARCHIVE = (
    ROOT
    / "probes"
    / "codex-0.148.0-alpha.9-plaintext-candidate-archive-20260817.json"
)
HISTORICAL_PREFLIGHT = (
    ROOT
    / "probes"
    / "codex-0.148.0-alpha.9-plaintext-live-selection-preflight.json"
)
SHA256 = re.compile(r"^[0-9a-f]{64}$")


class CandidateLiveSelectionIncidentTests(unittest.TestCase):
    def setUp(self) -> None:
        self.incident = json.loads(INCIDENT.read_text(encoding="utf-8"))
        self.archive = json.loads(ARCHIVE.read_text(encoding="utf-8"))
        self.preflight = json.loads(HISTORICAL_PREFLIGHT.read_text(encoding="utf-8"))

    def test_incident_overrides_the_historical_gui_selection_plan(self) -> None:
        selection = self.incident["historical_selection"]
        failure = self.incident["failure"]
        self.assertEqual(selection["mechanism"], "GUI App process environment CODEX_CLI_PATH")
        self.assertTrue(selection["candidate_became_gui_app_server"])
        self.assertEqual(failure["classification"], "reserved_tool_schema_mismatch")
        self.assertIn("collaboration.followup_task", failure["server_error"])
        self.assertFalse(failure["plaintext_assignment_delivered"])
        self.assertFalse(failure["qualifies_p1"])
        self.assertEqual(
            self.preflight["selection_seam"]["wrapper_sha256"],
            selection["historical_wrapper_sha256"],
        )

    def test_recovery_is_exact_but_not_a_qualification_receipt(self) -> None:
        recovery = self.incident["recovery"]
        self.assertTrue(recovery["user_verified"])
        self.assertTrue(recovery["launchd_job_absent"])
        self.assertTrue(recovery["launchctl_codex_cli_path_absent"])
        self.assertTrue(recovery["official_app_server_signature_valid"])
        self.assertTrue(recovery["candidate_process_absent"])
        self.assertFalse(recovery["is_candidate_self_rollback_qualification"])

    def test_current_wrapper_cannot_be_a_gui_app_server(self) -> None:
        hardened = self.incident["hardened_wrapper"]
        wrapper = ROOT / hardened["path"]
        self.assertEqual(hashlib.sha256(wrapper.read_bytes()).hexdigest(), hardened["sha256"])
        self.assertNotEqual(
            hardened["sha256"],
            self.incident["historical_selection"]["historical_wrapper_sha256"],
        )
        self.assertFalse(hardened["can_be_used_as_gui_codex_cli_path"])
        self.assertIn("app-server", hardened["forbidden_entry_points"])
        self.assertEqual(hardened["forced_posture"]["tool_namespace"], "g4_assignment")
        self.assertEqual(hardened["forced_posture"]["default_sandbox"], "read-only")
        self.assertEqual(
            hardened["forced_posture"]["guarded_write_probe_sandbox"],
            "workspace-write",
        )
        self.assertEqual(
            hardened["forced_posture"]["guarded_write_probe_root_namespace"],
            "/private/tmp/codex-g4-write-*",
        )
        self.assertEqual(
            hardened["forced_posture"]["guarded_auto_compact_limit"],
            20000,
        )
        self.assertEqual(
            hardened["forced_posture"][
                "guarded_failed_apply_patch_callback_authorization"
            ],
            "CODEX_G4_FAILED_PATCH_CALLBACK_PROBE_AUTHORIZED="
            "schema1-root-failed-apply-patch",
        )
        self.assertEqual(
            hardened["forced_posture"]["guarded_failed_apply_patch_root_namespace"],
            "/private/tmp/codex-g4-write-posttool-*",
        )
        self.assertTrue(
            hardened["forced_posture"]["guarded_failed_apply_patch_code_mode_host"]
        )
        self.assertFalse(hardened["forced_posture"]["code_mode_host"])
        self.assertEqual(hardened["forced_posture"]["caller_config_override"], "deny")

    def test_non_reserved_smoke_is_server_acceptance_only(self) -> None:
        smoke = self.incident["isolated_server_schema_smoke"]
        self.assertTrue(smoke["ephemeral"])
        self.assertTrue(smoke["ignored_user_config"])
        self.assertEqual(smoke["tool_namespace"], "g4_assignment")
        self.assertEqual(smoke["assistant_result"], "READY")
        self.assertEqual(smoke["tool_calls"], 0)
        self.assertFalse(smoke["http_400_observed"])
        self.assertIn("no spawn", smoke["scope"])

    def test_archive_binds_patch_build_and_all_candidate_receipts(self) -> None:
        patch = self.archive["patch"]
        patch_bytes = (ROOT / patch["path"]).read_bytes()
        self.assertEqual(hashlib.sha256(patch_bytes).hexdigest(), patch["sha256"])
        self.assertTrue(patch["byte_identical_to_temporary_tree_diff"])
        self.assertEqual(len(self.archive["source"]["modified_paths"]), 12)
        self.assertNotIn("Cargo.lock", self.archive["source"]["modified_paths"])
        receipts = self.archive["writer_receipt_manifest"]["receipts"]
        self.assertEqual(len(receipts), self.archive["writer_receipt_manifest"]["count"])
        self.assertEqual(len(receipts), 13)
        for receipt in receipts:
            self.assertTrue(SHA256.fullmatch(receipt["source_sha256"]))
            self.assertTrue(SHA256.fullmatch(receipt["claim_sha256"]))
            self.assertTrue(SHA256.fullmatch(receipt["before_snapshot_sha256"]))
            self.assertTrue(SHA256.fullmatch(receipt["after_snapshot_sha256"]))
            self.assertTrue(receipt["paths"])

    def test_incident_cannot_promote_phase_or_direct_write(self) -> None:
        verdict = self.incident["verdict"]
        self.assertFalse(verdict["phase1_complete"])
        self.assertFalse(verdict["p1_complete"])
        self.assertFalse(verdict["direct_write_qualified"])
        self.assertFalse(verdict["phase2_open"])
        self.assertFalse(verdict["phase3_open"])
        self.assertFalse(self.incident["failure"]["credential_value_observed_or_recorded"])
        self.assertFalse(self.archive["privacy"]["credential_value_read_or_copied"])


if __name__ == "__main__":
    unittest.main()
