import hashlib
import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
RECEIPT = (
    ROOT
    / "probes"
    / "current-signed-runtime-g4-closed-tool-catalog-source-candidate.json"
)
RUNTIME_INDEX = ROOT / "probes" / "codex-runtime-evidence-index.json"


class CurrentG4ClosedToolCatalogSourceCandidateTests(unittest.TestCase):
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
        self.assertEqual(reconstruction["reverse_apply_check"], "pass")

    def test_exact_role_catalog_is_closed_after_all_contributors(self):
        contract = self.receipt["tool_catalog_contract"]
        self.assertEqual(contract["role"], "g4_qualification_probe_worker")
        self.assertEqual(
            contract["identity_source"], "TurnContext.session_source.get_agent_role"
        )
        self.assertTrue(contract["exact_role_match_required"])
        self.assertEqual(contract["tool_mode"], "direct")
        self.assertEqual(
            contract["configured_v2_namespace_allowlist"], ["list_agents"]
        )
        self.assertIn("apply_patch", contract["default_namespace_allowlist"])
        self.assertTrue(
            contract[
                "registry_pruned_after_core_mcp_extension_dynamic_and_tool_search_contributions"
            ]
        )
        self.assertTrue(contract["hosted_specs_removed"])
        self.assertTrue(contract["code_mode_tool_map_empty"])
        self.assertFalse(contract["requires_code_mode_worker"])
        self.assertFalse(contract["can_manage_children"])
        self.assertFalse(contract["grants_mutation_authority"])
        self.assertFalse(contract["changes_non_g4_roles"])
        for anchor in (
            "G4_QUALIFICATION_PROBE_ROLE",
            "g4_qualification_tool_allowed",
            "registry.retain",
            "hosted_specs.clear",
            "exact_g4_qualification_role_has_closed_tool_catalog",
            'ToolName::namespaced("g4_assignment", "list_agents")',
        ):
            self.assertIn(anchor, self.patch_text)

    def test_verification_covers_open_optional_surfaces_and_regression(self):
        verification = self.receipt["verification"]
        self.assertIn("pass: 1 selected test", verification["focused_rust"]["result"])
        self.assertEqual(
            verification["spec_plan_regression"]["result"], "pass: 59 tests"
        )
        for surface in (
            "ShellTool",
            "CodeModeOnly",
            "MultiAgentV2",
            "MCP runtime",
            "extension runtime",
            "dynamic runtime",
        ):
            self.assertIn(surface, verification["tested_open_surfaces"])

    def test_candidate_and_phase_boundaries_remain_isolated(self):
        candidate = self.receipt["candidate"]
        live = self.receipt["live_boundary"]
        verdict = self.receipt["verdict"]
        self.assertFalse(candidate["selected_as_gui_app_server"])
        self.assertFalse(candidate["installed_live"])
        self.assertTrue(candidate["build_cache_removed_after_verification"])
        self.assertTrue(candidate["candidate_preserved_after_cleanup"])
        self.assertTrue(live["exact_role_apply_patch_call_observed"])
        self.assertTrue(live["pretool_denied_before_execution"])
        self.assertFalse(live["target_bytes_mutated"])
        self.assertTrue(verdict["source_closed_catalog_qualified"])
        self.assertFalse(verdict["full_live_catalog_absence_qualified"])
        self.assertFalse(verdict["positive_child_write_qualified"])
        self.assertFalse(verdict["strong_mutation_quiescence_qualified"])
        self.assertFalse(verdict["phase1_complete"])
        self.assertFalse(verdict["direct_write_qualified"])
        self.assertEqual(verdict["phase2_state"], "closed")
        self.assertEqual(verdict["phase3_state"], "closed")


if __name__ == "__main__":
    unittest.main()
