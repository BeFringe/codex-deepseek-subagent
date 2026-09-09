import hashlib
import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
RECEIPT = (
    ROOT
    / "probes"
    / "current-signed-runtime-g4-required-pretool-fail-closed-source-candidate.json"
)
RUNTIME_INDEX = ROOT / "probes" / "codex-runtime-evidence-index.json"


class CurrentG4RequiredPreToolFailClosedSourceCandidateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.receipt = json.loads(RECEIPT.read_text(encoding="utf-8"))
        cls.runtime_index = json.loads(RUNTIME_INDEX.read_text(encoding="utf-8"))
        reconstruction = cls.receipt["reconstruction"]
        cls.patch_path = ROOT / reconstruction["patch"]
        cls.patch_bytes = cls.patch_path.read_bytes()
        cls.patch_text = cls.patch_bytes.decode("utf-8")

    def test_source_identity_uses_current_semantic_runtime_role(self):
        current_role = self.runtime_index["current_runtime_role"]
        runtime = self.runtime_index["runtime_roles"][current_role]
        source = self.receipt["source"]

        self.assertEqual(source["commit"], runtime["source_commit"])
        self.assertEqual(
            source["semantic_runtime_version"],
            f"codex-cli {runtime['codex_version']}",
        )

    def test_predecessor_and_patch_are_hash_bound(self):
        predecessor = self.receipt["predecessor"]
        predecessor_path = ROOT / predecessor["receipt"]
        self.assertEqual(
            hashlib.sha256(predecessor_path.read_bytes()).hexdigest(),
            predecessor["receipt_sha256"],
        )

        reconstruction = self.receipt["reconstruction"]
        self.assertEqual(
            hashlib.sha256(self.patch_bytes).hexdigest(),
            reconstruction["patch_sha256"],
        )
        self.assertEqual(len(self.patch_bytes), reconstruction["patch_bytes"])
        self.assertEqual(
            len(self.patch_text.splitlines()), reconstruction["patch_lines"]
        )
        self.assertEqual(self.patch_text.count("--- a/"), 3)
        self.assertEqual(self.patch_text.count("+++ b/"), 3)
        self.assertEqual(reconstruction["changed_path_count"], 3)
        self.assertNotIn("Cargo.lock", self.patch_text)
        self.assertFalse(reconstruction["cargo_lock_included"])
        self.assertEqual(reconstruction["apply_mode"], "git apply --unidiff-zero")
        self.assertEqual(reconstruction["forward_apply_check"], "pass")
        self.assertEqual(reconstruction["reverse_apply_check"], "pass")
        self.assertTrue(reconstruction["forward_result_matches_candidate_bytes"])

    def test_exact_qualification_actors_require_decisive_control_results(self):
        contract = self.receipt["required_pretool_contract"]
        self.assertIn(
            "exact g4_qualification_probe_worker child role", contract["scope"]
        )
        self.assertTrue(contract["required_for_each_hook_visible_closed_catalog_tool"])
        self.assertEqual(contract["minimum_synchronous_control_handlers"], 1)
        self.assertTrue(contract["all_selected_control_handlers_must_adjudicate"])
        self.assertTrue(contract["denial_occurs_before_tool_handler"])
        self.assertFalse(contract["ordinary_codex_hook_failure_behavior_changed"])
        self.assertFalse(contract["grants_mutation_authority"])
        self.assertFalse(contract["establishes_same_uid_or_os_trust"])
        for rejected in (
            "no matching synchronous control handler",
            "handler spawn, timeout, or execution error",
            "exit 0 with empty or non-JSON stdout",
            "malformed JSON-like stdout",
            "fewer adjudications than selected control handlers",
        ):
            self.assertIn(rejected, contract["rejected_as_indeterminate"])
        for anchor in (
            "control_handlers_matched",
            "control_handlers_adjudicated",
            "control_output_valid",
            "g4_pre_tool_use_mediation_incomplete",
            "Stock sessions retain the upstream fail-open behavior",
            "exact_g4_parent_blocks_when_pre_tool_use_has_no_control_handler",
            "ordinary_actor_keeps_no_handler_pre_tool_use_behavior",
        ):
            self.assertIn(anchor, self.patch_text)

    def test_source_progress_does_not_promote_live_or_phase_state(self):
        live = self.receipt["live_boundary"]
        verdict = self.receipt["verdict"]

        self.assertFalse(live["candidate_rebuilt"])
        self.assertFalse(live["candidate_selected_as_gui_app_server"])
        self.assertFalse(live["candidate_installed_live"])
        self.assertTrue(live["source_required_hook_fail_closed_qualified"])
        self.assertFalse(live["live_missing_handler_denial_qualified"])
        self.assertFalse(live["live_failed_handler_denial_qualified"])
        self.assertFalse(live["independent_host_control_qualified"])
        self.assertFalse(live["same_uid_hostile_mutation_qualified"])
        self.assertTrue(verdict["required_pretool_source_contract_qualified"])
        self.assertFalse(verdict["p4_qualified"])
        self.assertFalse(verdict["phase1_complete"])
        self.assertFalse(verdict["direct_write_qualified"])
        self.assertEqual(verdict["phase2_state"], "closed")
        self.assertEqual(verdict["phase3_state"], "closed")


if __name__ == "__main__":
    unittest.main()
