import hashlib
import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
RECEIPT = (
    ROOT
    / "probes"
    / "current-signed-runtime-g4-live-catalog-receipt-source-candidate.json"
)
RUNTIME_INDEX = ROOT / "probes" / "codex-runtime-evidence-index.json"


class CurrentG4LiveCatalogReceiptSourceCandidateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.receipt = json.loads(RECEIPT.read_text(encoding="utf-8"))
        cls.runtime_index = json.loads(RUNTIME_INDEX.read_text(encoding="utf-8"))
        reconstruction = cls.receipt["reconstruction"]
        cls.patch_path = ROOT / reconstruction["patch"]
        cls.patch_bytes = cls.patch_path.read_bytes()
        cls.patch_text = cls.patch_bytes.decode("utf-8")

    def test_source_identity_tracks_current_semantic_runtime(self):
        current_role = self.runtime_index["current_runtime_role"]
        runtime = self.runtime_index["runtime_roles"][current_role]
        source = self.receipt["source"]
        self.assertEqual(source["commit"], runtime["source_commit"])
        self.assertEqual(
            source["semantic_runtime_version"],
            f"codex-cli {runtime['codex_version']}",
        )

    def test_patch_is_exact_reconstructable_and_lockfile_free(self):
        reconstruction = self.receipt["reconstruction"]
        self.assertEqual(
            hashlib.sha256(self.patch_bytes).hexdigest(),
            reconstruction["patch_sha256"],
        )
        self.assertEqual(len(self.patch_bytes), reconstruction["patch_bytes"])
        self.assertEqual(
            len(self.patch_text.splitlines()), reconstruction["patch_lines"]
        )
        self.assertEqual(
            self.patch_text.count("diff --git "),
            reconstruction["changed_path_count"],
        )
        self.assertNotIn("Cargo.lock", self.patch_text)
        self.assertFalse(reconstruction["cargo_lock_included"])
        self.assertEqual(
            reconstruction["forward_apply_check_on_pristine_source"], "pass"
        )
        self.assertEqual(
            reconstruction["reverse_apply_check_on_candidate_source"], "pass"
        )

    def test_runtime_receipt_is_exact_role_opt_in_and_non_mutating(self):
        contract = self.receipt["runtime_receipt_contract"]
        self.assertEqual(
            contract["environment_opt_in"],
            "CODEX_G4_TOOL_CATALOG_RECEIPT=stderr-v1",
        )
        self.assertEqual(contract["exact_role"], "g4_qualification_probe_worker")
        self.assertTrue(contract["requires_thread_spawn_source"])
        self.assertTrue(contract["requires_parent_thread_id"])
        self.assertTrue(contract["requires_canonical_agent_path"])
        self.assertTrue(contract["requires_nonempty_turn_id"])
        self.assertTrue(contract["silent_for_root_and_other_roles"])
        self.assertFalse(contract["writes_files"])
        self.assertFalse(contract["records_credentials"])
        for anchor in (
            "G4_CATALOG_RECEIPT_ENV",
            "G4_CATALOG_RECEIPT_OPT_IN",
            "G4_TOOL_CATALOG_RECEIPT_V1 ",
            "SessionSource::SubAgent(SubAgentSource::ThreadSpawn",
            "if turn_context.sub_id.is_empty()",
            "qualification_catalog_receipt",
            "finalized_tool_router_after_all_contributors",
            "g4_catalog_receipt::emit_if_requested",
        ):
            self.assertIn(anchor, self.patch_text)

    def test_source_and_live_verification_preserve_boundaries(self):
        verification = self.receipt["verification"]
        candidate = self.receipt["candidate"]
        live = self.receipt["live_boundary"]
        verdict = self.receipt["verdict"]
        self.assertEqual(verification["focused_rust"]["result"], "pass: 1 selected test; 2454 filtered out")
        self.assertEqual(verification["spec_plan_regression"]["result"], "pass: 59 tests")
        self.assertEqual(verification["candidate_build"]["result"], "pass")
        self.assertTrue(candidate["build_cache_removed_after_verification"])
        self.assertTrue(candidate["candidate_preserved_after_cleanup"])
        self.assertFalse(candidate["selected_as_gui_app_server"])
        self.assertFalse(candidate["installed_live"])
        self.assertEqual(live["real_child_receipt_count"], 2)
        self.assertTrue(live["real_child_receipts_identical"])
        self.assertFalse(live["empty_turn_receipts_observed"])
        self.assertEqual(live["candidate_exit_code"], 0)
        self.assertTrue(verdict["source_runtime_catalog_receipt_qualified"])
        self.assertTrue(verdict["exact_g4_final_router_catalog_absence_qualified"])
        self.assertFalse(verdict["parent_and_host_control_negative_space_qualified"])
        self.assertFalse(verdict["strong_mutation_quiescence_qualified"])
        self.assertFalse(verdict["phase1_complete"])
        self.assertFalse(verdict["direct_write_qualified"])
        self.assertEqual(verdict["phase2_state"], "closed")
        self.assertEqual(verdict["phase3_state"], "closed")


if __name__ == "__main__":
    unittest.main()
