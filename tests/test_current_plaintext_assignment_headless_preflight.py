from __future__ import annotations

import json
from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]
PREFLIGHT = (
    ROOT
    / "probes"
    / "current-signed-runtime-plaintext-assignment-seam-headless-preflight.json"
)
SOURCE_RECEIPT = (
    ROOT
    / "probes"
    / "current-signed-runtime-plaintext-assignment-seam-source-candidate.json"
)
RUNTIME_INDEX = ROOT / "probes" / "codex-runtime-evidence-index.json"


class CurrentPlaintextAssignmentHeadlessPreflightTests(unittest.TestCase):
    def setUp(self) -> None:
        self.preflight = json.loads(PREFLIGHT.read_text(encoding="utf-8"))
        self.source = json.loads(SOURCE_RECEIPT.read_text(encoding="utf-8"))
        self.runtime_index = json.loads(RUNTIME_INDEX.read_text(encoding="utf-8"))

    def test_preflight_resolves_the_semantic_current_runtime(self) -> None:
        current = self.runtime_index["runtime_roles"]["current_signed_runtime"]
        build = self.preflight["build"]

        self.assertEqual(self.preflight["runtime_role"], "current_signed_runtime")
        self.assertEqual(self.preflight["base_source_commit"], current["source_commit"])
        self.assertEqual(build["reported_version"], current["codex_version"])
        self.assertEqual(self.source["codex_version"], current["codex_version"])
        self.assertEqual(self.source["base_source_commit"], current["source_commit"])

    def test_binary_build_receipt_is_structurally_exact(self) -> None:
        build = self.preflight["build"]

        self.assertEqual(build["command"], "cargo build -p codex-cli --bin codex")
        self.assertEqual(build["exit_code"], 0)
        self.assertEqual(build["binary_format"], "Mach-O 64-bit executable arm64")
        self.assertRegex(build["binary_sha256"], re.compile(r"^[0-9a-f]{64}$"))
        self.assertGreater(build["binary_bytes"], 0)
        self.assertEqual(build["signature_kind"], "adhoc-linker-signed")
        self.assertFalse(build["team_identifier_present"])
        self.assertTrue(self.preflight["storage"]["cargo_target_deleted_after_copy"])

    def test_build_does_not_claim_installation_or_live_qualification(self) -> None:
        selection = self.preflight["selection_boundaries"]
        qualification = self.preflight["qualification"]

        self.assertTrue(selection["invoked_by_absolute_path_for_version_check_only"])
        self.assertFalse(selection["candidate_installed"])
        self.assertFalse(selection["candidate_selected_for_gui_app_server"])
        self.assertFalse(selection["gui_app_restarted"])
        self.assertFalse(selection["codex_cli_path_modified"])
        self.assertFalse(selection["live_config_modified"])
        self.assertFalse(selection["headless_agent_turn_started"])
        self.assertFalse(selection["credential_values_read_or_stored"])
        self.assertTrue(qualification["source_candidate_qualified"])
        self.assertTrue(qualification["headless_binary_build_qualified"])
        self.assertFalse(qualification["plaintext_assignment_seam_qualified"])
        self.assertFalse(qualification["live_sessionmeta_identity_qualified"])
        self.assertFalse(qualification["phase1_complete"])
        self.assertFalse(qualification["direct_write_qualified"])
        self.assertEqual(qualification["phase2_state"], "closed")
        self.assertEqual(qualification["phase3_state"], "closed")


if __name__ == "__main__":
    unittest.main()
