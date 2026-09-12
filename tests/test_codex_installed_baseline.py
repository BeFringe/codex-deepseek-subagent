import json
import importlib.util
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
INDEX_SCRIPT = ROOT / "probes" / "check_runtime_evidence_index.py"

SPEC = importlib.util.spec_from_file_location("check_runtime_evidence_index", INDEX_SCRIPT)
runtime_evidence = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(runtime_evidence)

RELEASE_INDEX = runtime_evidence.load_index()
BASELINE = runtime_evidence.evidence_path(RELEASE_INDEX, "installed_baseline")
COMPONENTS = runtime_evidence.evidence_path(RELEASE_INDEX, "component_boundaries")


class CodexInstalledBaselineTests(unittest.TestCase):
    def setUp(self):
        self.baseline = json.loads(BASELINE.read_text(encoding="utf-8"))
        self.components = json.loads(COMPONENTS.read_text(encoding="utf-8"))

    def test_installed_versions_match_pinned_source_contract(self):
        version = self.components["codex_version"]

        self.assertEqual(self.baseline["standalone_cli"]["reported_version"], version)
        self.assertEqual(
            self.baseline["codex_app"]["app_server_reported_version"], version
        )
        self.assertTrue(
            self.baseline["verdict"]["installed_cli_and_app_server_semver_converged"]
        )
        self.assertTrue(self.baseline["codex_app"]["bundle_signature_valid"])
        self.assertTrue(
            self.baseline["codex_app"]["running_app_server_uses_bundle_binary"]
        )
        self.assertFalse(self.baseline["codex_app"]["candidate_or_wrapper_selected"])
        self.assertFalse(
            self.baseline["selection_environment"]["launchd_CODEX_CLI_PATH_set"]
        )
        self.assertFalse(
            self.baseline["selection_environment"]["task_process_CODEX_CLI_PATH_set"]
        )

    def test_historical_sessionmeta_is_not_promoted(self):
        sessionmeta = self.baseline["sessionmeta"]
        verdict = self.baseline["verdict"]

        self.assertEqual(
            sessionmeta["current_long_lived_thread_cli_version"],
            runtime_evidence.runtime_identity(
                RELEASE_INDEX, "migration_handoff_runtime"
            )["codex_version"],
        )
        self.assertTrue(sessionmeta["current_thread_is_historical_provenance"])
        self.assertFalse(sessionmeta["recent_fresh_current_signed_root_observed"])
        self.assertTrue(sessionmeta["fresh_current_signed_identity_cohort_required"])
        self.assertTrue(verdict["runtime_guard_may_accept_current_signed_sessionmeta"])
        self.assertFalse(verdict["current_thread_may_be_relabelled_as_current_signed"])
        self.assertFalse(verdict["live_current_signed_child_identity_qualified"])

    def test_install_convergence_cannot_promote_phase(self):
        verdict = self.baseline["verdict"]

        self.assertFalse(verdict["native_heterogeneous_child_restored"])
        self.assertFalse(verdict["phase1_complete"])
        self.assertFalse(verdict["direct_write_qualified"])
        self.assertEqual(verdict["phase2_state"], "closed")
        self.assertEqual(verdict["phase3_state"], "closed")


if __name__ == "__main__":
    unittest.main()
