import hashlib
import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
RECEIPT = (
    ROOT
    / "probes"
    / "current-signed-runtime-session-close-source-candidate.json"
)


class CurrentSessionCloseSourceCandidateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.receipt = json.loads(RECEIPT.read_text(encoding="utf-8"))
        reconstruction = cls.receipt["reconstruction"]
        cls.patch_path = ROOT / reconstruction["patch"]
        cls.patch_bytes = cls.patch_path.read_bytes()
        cls.patch_text = cls.patch_bytes.decode("utf-8")

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

    def test_v2_close_reuses_host_shutdown_without_weakening_interrupt(self):
        contract = self.receipt["host_contract"]
        self.assertEqual(contract["tool"], "close_agent")
        self.assertEqual(contract["multi_agent_version"], "V2")
        self.assertIn("shutdown_agent_tree", contract["native_primitive"])
        self.assertIn("wait_until_terminated", contract["native_primitive"])
        self.assertTrue(contract["session_loop_terminated"])
        self.assertTrue(contract["live_descendant_session_loops_terminated"])
        self.assertFalse(contract["process_tree_quiescence_claimed"])
        self.assertFalse(contract["filesystem_mutation_quiescence_claimed"])
        self.assertFalse(contract["interrupt_agent_semantics_changed"])
        self.assertIn("create_close_agent_tool_v2", self.patch_text)
        self.assertIn("CloseAgentHandlerV2", self.patch_text)
        self.assertIn("process_tree_quiescence_claimed: false", self.patch_text)

    def test_source_observation_stays_below_mutation_quiescence(self):
        observation = self.receipt["source_observation"]
        self.assertTrue(observation["shutdown_waits_for_session_loop_termination"])
        self.assertFalse(
            observation["tracked_unified_exec_termination_is_confirmed_exit_barrier"]
        )
        self.assertFalse(observation["detached_or_untracked_descendants_are_covered"])
        self.assertIn("closed mutation catalog", observation["consequence"])
        self.assertIn("zero in-flight writer claims", observation["consequence"])
        self.assertIn("fresh post-termination disk barrier", observation["consequence"])

    def test_candidate_is_isolated_and_phase1_remains_closed(self):
        candidate = self.receipt["candidate"]
        source = self.receipt["source"]
        live = self.receipt["live_probe"]
        self.assertEqual(source["semantic_runtime_version"], "codex-cli 0.153.4")
        self.assertFalse(candidate["selected_as_gui_app_server"])
        self.assertFalse(candidate["installed_live"])
        self.assertEqual(live["state"], "native_session_close_observed")
        self.assertTrue(live["native_host_session_termination_primitive_qualified"])
        self.assertFalse(live["strong_mutation_quiescence_qualified"])
        self.assertFalse(live["phase1_complete"])
        self.assertFalse(live["direct_write_qualified"])


if __name__ == "__main__":
    unittest.main()
