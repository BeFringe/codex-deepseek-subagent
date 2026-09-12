import copy
import datetime as dt
import hashlib
import importlib.util
import json
from pathlib import Path, PurePosixPath
import re
import sys
import unittest
from historical_source import historical_sha256


ROOT = Path(__file__).resolve().parents[1]
RECEIPT = ROOT / "probes" / "g4-live-nonempty-tracked-process-termination-20260909.json"
RECONCILER = ROOT / "probes" / "reconcile_g4_nonempty_tracked_process_close.py"
WRAPPER = ROOT / "probes" / "codex_plaintext_candidate_wrapper.sh"
PROMPT_BUILDER = ROOT / "probes" / "build_p5b_tracked_process_probe_prompt.py"


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


reconciler = load_module("g4_nonempty_tracked_process_reconciler", RECONCILER)


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical_sha256(value):
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def timestamp(value):
    return dt.datetime.fromisoformat(value)


class G4LiveNonemptyTrackedProcessTerminationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.receipt = json.loads(RECEIPT.read_text(encoding="utf-8"))

    def test_probe_guard_and_reconciler_are_hash_bound_without_runtime_pin(self):
        guard = self.receipt["probe_guard"]
        runtime = self.receipt["runtime"]
        self.assertRegex(guard["wrapper_sha256"], r"^[0-9a-f]{64}$")
        current_wrapper = WRAPPER.read_text(encoding="utf-8")
        self.assertIn("CODEX_G4_CANDIDATE_SHA256", current_wrapper)
        self.assertIn("CODEX_G4_P5B_TRACKED_TERMINATION_PROBE_AUTHORIZED", current_wrapper)
        self.assertIn("GUI and server entry points are forbidden", current_wrapper)
        self.assertEqual(guard["prompt_builder_sha256"], historical_sha256(PROMPT_BUILDER))
        self.assertEqual(self.receipt["reconciler"]["sha256"], sha256(RECONCILER))
        self.assertTrue(guard["candidate_and_code_mode_host_sha256_bound"])
        self.assertRegex(
            runtime["codex_semantic_version"],
            r"^[0-9]+\.[0-9]+\.[0-9]+(?:[-+][0-9A-Za-z.-]+)?$",
        )
        self.assertNotIn("0.153.4", RECONCILER.read_text(encoding="utf-8"))
        self.assertIn("candidate_selection_path", runtime)
        self.assertIn("candidate_resolved_path", runtime)
        self.assertIn("code_mode_host_selection_path", runtime)
        self.assertIn("code_mode_host_resolved_path", runtime)
        self.assertTrue(runtime["code_mode_host_selection_path"].endswith("codex-code-mode-host"))
        self.assertEqual(runtime["candidate_exit_code"], 0)
        self.assertFalse(runtime["gui_app_server_selected"])
        self.assertFalse(runtime["credential_value_observed"])

    def test_real_sessionmeta_identity_and_native_lifecycle_join_exactly(self):
        identity = self.receipt["identity"]
        lifecycle = self.receipt["native_lifecycle"]
        child = identity["child_thread_id"]
        path = identity["canonical_agent_path"]
        self.assertEqual(identity["runtime_session_id"], identity["parent_thread_id"])
        self.assertEqual(path, f"/root/{identity['requested_task_name']}")
        self.assertEqual(identity["agent_type"], "worker")
        self.assertEqual(lifecycle["pre_close_status"], "running")
        self.assertTrue(lifecycle["wait_timed_out"])
        self.assertTrue(lifecycle["target_absent_from_post_close_tree"])
        close = lifecycle["close_receipt"]
        process_id = reconciler.validate_close_receipt(close, child, path)
        self.assertEqual(process_id, lifecycle["tracked_process_id"])
        self.assertEqual(lifecycle["close_receipt_sha256"], canonical_sha256(close))
        self.assertEqual(
            close["tracked_process_ids_by_thread"],
            close["confirmed_exit_process_ids_by_thread"],
        )
        self.assertEqual(close["unconfirmed_exit_process_ids_by_thread"], {child: []})
        self.assertEqual(close["unresolved_start_process_ids_by_thread"], {child: []})

    def test_process_exit_witness_is_inside_close_and_negative_mutations_fail(self):
        lifecycle = self.receipt["native_lifecycle"]
        process = self.receipt["child_process"]
        self.assertEqual(process["process_id"], lifecycle["tracked_process_id"])
        self.assertTrue(process["start_session_id_equals_tracked_process_id"])
        self.assertEqual(process["process_exit_code"], 137)
        self.assertTrue(process["process_exit_observed_before_close_return"])
        self.assertEqual(process["turn_aborted_reason"], "interrupted")
        self.assertLess(timestamp(process["poll_called_at"]), timestamp(lifecycle["close_called_at"]))
        self.assertLess(timestamp(lifecycle["close_called_at"]), timestamp(process["poll_returned_at"]))
        self.assertLess(timestamp(process["poll_returned_at"]), timestamp(process["turn_aborted_at"]))
        self.assertLess(timestamp(process["turn_aborted_at"]), timestamp(lifecycle["close_returned_at"]))

        close = copy.deepcopy(lifecycle["close_receipt"])
        child = self.receipt["identity"]["child_thread_id"]
        close["confirmed_exit_process_ids_by_thread"] = {child: []}
        with self.assertRaisesRegex(
            reconciler.ReconciliationError,
            "one exact tracked process exit",
        ):
            reconciler.validate_close_receipt(
                close,
                child,
                self.receipt["identity"]["canonical_agent_path"],
            )

    def test_raw_artifacts_and_two_point_host_barrier_are_frozen(self):
        for artifact in self.receipt["raw_artifacts"].values():
            self.assertRegex(artifact["sha256"], r"^[0-9a-f]{64}$")
            self.assertGreater(artifact["line_count"], 0)
            self.assertTrue(PurePosixPath(artifact["path"]).is_absolute())
        barrier = self.receipt["post_termination_host_barrier"]
        observations = barrier["observations"]
        self.assertEqual(len(observations), 2)
        self.assertLess(observations[0]["observed_at_ns"], observations[1]["observed_at_ns"])
        self.assertEqual(observations[0]["head"], observations[1]["head"])
        self.assertEqual(observations[0]["tree"], observations[1]["tree"])
        for observation in observations:
            self.assertEqual(observation["git_status_short"], "")
            self.assertFalse(observation["tracked_process_id_present"])
            self.assertEqual(observation["marked_process_match_count"], 0)
            self.assertEqual(observation["candidate_open_file_count"], 0)
        self.assertTrue(barrier["stable_git_frontier"])
        self.assertTrue(barrier["tracked_process_absent"])
        self.assertTrue(barrier["exact_marker_absent"])
        self.assertFalse(barrier["strong_global_process_tree_quiescence_claimed"])

    def test_scope_is_a_p5b_contribution_not_g4_or_phase_promotion(self):
        verdict = self.receipt["verdict"]
        self.assertTrue(verdict["native_standard_worker_nonempty_tracked_process_exit_qualified"])
        self.assertTrue(verdict["real_sessionmeta_identity_join_qualified"])
        self.assertTrue(verdict["post_termination_host_barrier_qualified_for_this_run"])
        self.assertFalse(verdict["g4_closed_catalog_process_surface_qualified"])
        self.assertFalse(verdict["mutation_capable_actor_termination_qualified"])
        self.assertFalse(verdict["detached_or_untracked_process_quiescence_qualified"])
        self.assertFalse(verdict["strong_global_process_tree_quiescence_qualified"])
        self.assertEqual(verdict["p5b_state"], "partial")
        self.assertFalse(verdict["phase1_complete"])
        self.assertFalse(verdict["direct_write_qualified"])
        self.assertEqual(verdict["phase2_state"], "closed")
        self.assertEqual(verdict["phase3_state"], "closed")


if __name__ == "__main__":
    unittest.main()
