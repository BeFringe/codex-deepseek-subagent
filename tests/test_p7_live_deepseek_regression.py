from pathlib import Path
import importlib.util
import json
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]
RECEIPT_PATH = ROOT / "probes" / "p7-live-deepseek-regression-20260910.json"
SCRIPT_PATH = ROOT / "probes" / "adjudicate_p7_deepseek_regression_live.py"
RUNTIME_INDEX_PATH = ROOT / "probes" / "codex-runtime-evidence-index.json"
STATUS_PATH = ROOT / "probes" / "phase1-g4-status.json"
SHA256 = re.compile(r"^[0-9a-f]{64}$")

SPEC = importlib.util.spec_from_file_location(
    "adjudicate_p7_deepseek_regression_live", SCRIPT_PATH
)
module = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(module)


class P7LiveDeepSeekRegressionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.receipt = json.loads(RECEIPT_PATH.read_text(encoding="utf-8"))
        cls.runtime_index = json.loads(RUNTIME_INDEX_PATH.read_text(encoding="utf-8"))
        cls.status = json.loads(STATUS_PATH.read_text(encoding="utf-8"))

    def test_fresh_adjudicator_recomputes_the_native_loop(self):
        manifest = Path(self.receipt["raw_artifacts"]["manifest_path"])
        if not manifest.is_file():
            self.skipTest("originating-host raw live manifest is not present")
        try:
            fresh = module.adjudicate(manifest)
        except module.AdjudicationError as error:
            if "drifted" in str(error):
                self.skipTest(f"originating-host raw anchor drifted: {error}")
            raise
        for key in ("runtime", "credential_boundary", "transport", "identity", "native_loop", "disk_barrier", "verdict"):
            self.assertEqual(fresh[key], self.receipt[key])

    def test_frozen_receipt_retains_raw_manifest_identity_for_off_host_audit(self):
        raw = self.receipt["raw_artifacts"]
        self.assertTrue(raw["manifest_path"].startswith("/private/tmp/"))
        for field in (
            "manifest_sha256",
            "parent_rollout_sha256",
            "child_rollout_sha256",
            "candidate_stdout_sha256",
            "candidate_stderr_sha256",
        ):
            self.assertRegex(raw[field], SHA256)

    def test_parent_and_child_provider_identity_are_distinct_and_exact(self):
        identity = self.receipt["identity"]
        self.assertEqual(identity["parent_provider"], "openai")
        self.assertEqual(identity["child_provider"], "deepseek")
        self.assertEqual(identity["child_model"], "deepseek-v4-flash")
        self.assertEqual(identity["agent_type"], "v4_flash_worker")
        self.assertEqual(
            identity["canonical_agent_path"], "/root/p7_deepseek_readonly_3"
        )
        self.assertEqual(identity["depth"], 1)

    def test_one_shot_handoff_tool_result_wait_callback_and_disk_are_exact(self):
        transport = self.receipt["transport"]
        loop = self.receipt["native_loop"]
        disk = self.receipt["disk_barrier"]
        self.assertEqual(transport["assignment_transport"], "one-shot plaintext SubagentStart Hook")
        self.assertEqual(transport["wire_transport"], "responses-direct")
        self.assertTrue(transport["marker_absent_from_parent_prompt_and_spawn_message"])
        self.assertTrue(transport["handoff_consumed"])
        self.assertFalse(loop["wait_timed_out"])
        self.assertEqual(loop["child_tool_call_count"], 1)
        self.assertEqual(loop["third_nonempty_line"], "responses")
        self.assertEqual(
            loop["fixture_sha256"],
            "b7383fea044646d48d597239385c40246df3ef511a3486053d4711d171589bc1",
        )
        self.assertTrue(loop["callback_byte_exact"])
        self.assertEqual(disk["git_status_short"], "")
        self.assertEqual(disk["handoff_state_names"], [".v4_flash_worker.lock"])

    def test_runtime_is_semantic_and_credentials_remain_opaque(self):
        role = self.runtime_index["current_runtime_role"]
        runtime = self.runtime_index["runtime_roles"][role]
        self.assertEqual(self.receipt["runtime"]["semantic_role"], role)
        self.assertEqual(self.receipt["runtime"]["codex_version"], runtime["codex_version"])
        self.assertEqual(self.receipt["runtime"]["source_commit"], runtime["source_commit"])
        credential = self.receipt["credential_boundary"]
        self.assertTrue(credential["credential_present"])
        for field in (
            "credential_value_read",
            "credential_value_printed",
            "credential_value_hashed",
            "credential_value_retained",
            "credential_value_committed",
        ):
            self.assertFalse(credential[field])
        for field in ("assignment_sha256", "marker_sha256"):
            self.assertRegex(self.receipt["transport"][field], SHA256)

    def test_deepseek_and_later_install_receipts_advance_while_phases_stay_closed(self):
        verdict = self.receipt["verdict"]
        self.assertTrue(verdict["deepseek_regression_qualified"])
        self.assertFalse(verdict["phase1_complete"])
        self.assertFalse(verdict["direct_write_qualified"])
        self.assertEqual(verdict["phase2_state"], "closed")
        self.assertEqual(verdict["phase3_state"], "closed")
        gates = {gate["id"]: gate for gate in self.status["phase1"]["gates"]}
        receipts = {
            receipt["id"]: receipt for receipt in self.status["phase1"]["exit_receipts"]
        }
        self.assertEqual(gates["P7"]["state"], "partial")
        self.assertEqual(receipts["deepseek_regression"]["state"], "qualified")
        self.assertEqual(receipts["callback_continuity"]["state"], "qualified")
        self.assertEqual(receipts["posix_live"]["state"], "qualified")
        self.assertEqual(receipts["windows_live"]["state"], "pending")
        self.assertEqual(receipts["install_rollback"]["state"], "qualified")


if __name__ == "__main__":
    unittest.main()
