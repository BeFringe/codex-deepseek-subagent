import hashlib
import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
RECEIPT = (
    ROOT
    / "probes"
    / "current-signed-runtime-g4-trusted-catalog-origin-source-candidate.json"
)
RUNTIME_INDEX = ROOT / "probes" / "codex-runtime-evidence-index.json"


class CurrentG4TrustedCatalogOriginSourceCandidateTests(unittest.TestCase):
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

    def test_incremental_patch_is_hash_bound_and_reconstructable(self):
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

    def test_allowlist_is_bound_to_trusted_runtime_origin(self):
        contract = self.receipt["trusted_origin_contract"]
        self.assertIn("exact g4_qualification_probe_worker child", contract["scope"])
        self.assertIn("exact headless qualification parent", contract["scope"])
        self.assertFalse(contract["name_equality_alone_authorizes"])
        self.assertFalse(contract["trusted_runtime_absent_external_same_name_survives"])
        self.assertTrue(contract["removal_clears_trusted_membership"])
        self.assertFalse(contract["changes_non_qualification_catalogs"])
        self.assertFalse(contract["grants_mutation_authority"])
        for anchor in (
            "trusted_tool_names",
            "retain_trusted",
            "self.trusted_tool_names.insert(tool_name)",
            "exact_g4_qualification_role_rejects_allowlisted_external_name_spoofs",
            "exact_g4_qualification_parent_rejects_allowlisted_external_name_spoofs",
        ):
            self.assertIn(anchor, self.patch_text)

    def test_source_only_progress_does_not_promote_phase(self):
        live = self.receipt["live_boundary"]
        verdict = self.receipt["verdict"]
        self.assertFalse(live["candidate_rebuilt"])
        self.assertFalse(live["candidate_selected_as_gui_app_server"])
        self.assertFalse(live["candidate_installed_live"])
        self.assertTrue(live["source_invariant_qualified"])
        self.assertFalse(live["required_hook_fail_closed_qualified"])
        self.assertFalse(live["independent_host_control_qualified"])
        self.assertFalse(live["same_uid_hostile_mutation_qualified"])
        self.assertTrue(verdict["trusted_runtime_origin_binding_qualified"])
        self.assertFalse(verdict["p4_qualified"])
        self.assertFalse(verdict["phase1_complete"])
        self.assertFalse(verdict["direct_write_qualified"])
        self.assertEqual(verdict["phase2_state"], "closed")
        self.assertEqual(verdict["phase3_state"], "closed")


if __name__ == "__main__":
    unittest.main()
