from pathlib import Path
import hashlib
import importlib.util
import json
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]
RECEIPT_PATH = ROOT / "probes" / "p7-live-isolated-install-rollback-20260910.json"
ADJUDICATOR_PATH = ROOT / "probes" / "adjudicate_p7_isolated_install_rollback.py"
RUNNER_PATH = ROOT / "probes" / "run_p7_isolated_install_rollback.py"
WRAPPER_PATH = ROOT / "probes" / "codex_plaintext_candidate_wrapper.sh"
STATUS_PATH = ROOT / "probes" / "phase1-g4-status.json"
SHA256 = re.compile(r"^[0-9a-f]{64}$")

SPEC = importlib.util.spec_from_file_location(
    "adjudicate_p7_isolated_install_rollback", ADJUDICATOR_PATH
)
module = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(module)


class P7IsolatedInstallRollbackTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.receipt = json.loads(RECEIPT_PATH.read_text(encoding="utf-8"))
        cls.status = json.loads(STATUS_PATH.read_text(encoding="utf-8"))

    def test_harness_and_source_receipts_are_hash_bound(self):
        harness = self.receipt["harness"]
        paths = {
            "runner_sha256": RUNNER_PATH,
            "adjudicator_sha256": ADJUDICATOR_PATH,
            "wrapper_sha256": WRAPPER_PATH,
            "source_receipt_sha256": (
                ROOT / "probes" / "g4-live-failed-apply-patch-posttool-callback-20260908.json"
            ),
            "source_patch_sha256": (
                ROOT / "probes" / "current-signed-runtime-failed-apply-patch-posttool-source-candidate.patch"
            ),
        }
        for field, path in paths.items():
            self.assertEqual(
                harness[field], hashlib.sha256(path.read_bytes()).hexdigest(), field
            )

    def test_install_process_exercised_the_terminal_failed_tool_callback(self):
        reload_receipt = self.receipt["functional_reload"]
        self.assertEqual(reload_receipt["canonical_agent_path"], "/root")
        self.assertEqual(reload_receipt["tool_name"], "apply_patch")
        self.assertTrue(reload_receipt["pretool_authorized"])
        self.assertTrue(reload_receipt["posttool_callback_observed"])
        self.assertTrue(reload_receipt["writer_claim_released"])
        self.assertTrue(reload_receipt["failed_patch_left_disk_unchanged"])
        self.assertRegex(reload_receipt["tool_use_id"], r"^exec-[0-9a-f-]{36}$")

    def test_fresh_process_after_rollback_has_no_removed_hook_state(self):
        rollback = self.receipt["rollback"]
        self.assertTrue(rollback["fresh_process_after_rollback"])
        self.assertFalse(rollback["removed_hook_state_recreated"])
        self.assertTrue(rollback["managed_install_paths_absent"])
        self.assertTrue(rollback["diagnostic_state_archived"])
        self.assertTrue(rollback["live_app_and_v4_hashes_unchanged"])
        self.assertEqual(rollback["candidate_processes_after_barrier"], 0)
        self.assertNotEqual(
            self.receipt["functional_reload"]["positive_thread_id"],
            rollback["negative_thread_id"],
        )

    def test_parent_login_and_gui_boundaries_remain_exact(self):
        runtime = self.receipt["runtime"]
        credential = self.receipt["credential_boundary"]
        self.assertEqual(runtime["semantic_role"], "current_signed_runtime")
        self.assertEqual(runtime["parent_provider"], "openai")
        self.assertFalse(runtime["gui_app_server_selected"])
        self.assertFalse(runtime["codex_cli_path_modified"])
        self.assertTrue(credential["current_chatgpt_login_reused_by_symlink"])
        for field in (
            "credential_value_read",
            "credential_value_printed",
            "credential_value_hashed",
            "credential_value_committed",
        ):
            self.assertFalse(credential[field])

    def test_originating_host_can_replay_fresh_adjudication(self):
        manifest = Path(self.receipt["raw_artifacts"]["manifest_path"])
        if not manifest.is_file():
            self.skipTest("originating-host raw install manifest is not present")
        try:
            fresh = module.adjudicate(manifest)
        except module.AdjudicationError as error:
            if "drifted" in str(error):
                self.skipTest(f"originating-host raw anchor drifted: {error}")
            raise
        for field in (
            "runtime",
            "functional_reload",
            "rollback",
            "credential_boundary",
            "harness",
            "verdict",
        ):
            self.assertEqual(fresh[field], self.receipt[field])

    def test_frozen_raw_identities_are_portable_without_synthesizing_live_data(self):
        raw = self.receipt["raw_artifacts"]
        self.assertTrue(raw["manifest_path"].startswith("/private/tmp/"))
        for field, value in raw.items():
            if field.endswith("_sha256"):
                self.assertRegex(value, SHA256)

    def test_only_windows_keeps_phase1_fail_closed(self):
        gates = {gate["id"]: gate for gate in self.status["phase1"]["gates"]}
        receipts = {
            receipt["id"]: receipt for receipt in self.status["phase1"]["exit_receipts"]
        }
        self.assertFalse(self.receipt["verdict"]["phase1_complete"])
        self.assertFalse(self.receipt["verdict"]["direct_write_qualified"])
        self.assertEqual(gates["P7"]["state"], "qualified")
        self.assertEqual(receipts["windows_live"]["state"], "qualified")
        self.assertEqual(receipts["install_rollback"]["state"], "qualified")


if __name__ == "__main__":
    unittest.main()
