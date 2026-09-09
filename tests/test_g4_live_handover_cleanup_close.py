import hashlib
import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
RECEIPT = ROOT / "probes" / "g4-live-handover-cleanup-close-20260909.json"
RECONCILER = ROOT / "probes" / "reconcile_g4_handover_then_close.py"
WRAPPER = ROOT / "probes" / "codex_plaintext_handover_candidate_wrapper.sh"
PROMPT_BUILDER = ROOT / "probes" / "build_g4_write_probe_prompt.py"
OVERLAY_BUILDER = ROOT / "probes" / "build_child_write_probe_hook_overlay.py"
STATUS = ROOT / "probes" / "phase1-g4-status.json"


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


class G4LiveHandoverCleanupCloseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.receipt = json.loads(RECEIPT.read_text(encoding="utf-8"))
        cls.status = json.loads(STATUS.read_text(encoding="utf-8"))

    def test_live_guard_and_reconciler_are_hash_bound(self):
        guard = self.receipt["probe_guard"]
        reconciliation = self.receipt["durable_reconciliation"]
        self.assertEqual(guard["wrapper_sha256"], sha256(WRAPPER))
        self.assertEqual(guard["prompt_builder_sha256"], sha256(PROMPT_BUILDER))
        self.assertEqual(guard["overlay_builder_sha256"], sha256(OVERLAY_BUILDER))
        self.assertEqual(reconciliation["tool_sha256"], sha256(RECONCILER))
        self.assertEqual(
            guard["authorization"],
            "CODEX_G4_P5B_HANDOVER_PROBE_AUTHORIZED="
            "schema1-exact-barrier-replacement",
        )
        self.assertEqual(guard["authorization_ceiling"], "exact_post_quiescence_handover")
        self.assertFalse(self.receipt["runtime"]["gui_app_server_selected"])
        self.assertFalse(self.receipt["runtime"]["credential_value_observed"])
        self.assertTrue(guard["base_hooks_restored"])
        self.assertTrue(guard["v4_hook_preserved"])

    def test_replacement_consumes_the_exact_prior_barrier_and_frontier(self):
        handover = self.receipt["ownership_handover"]
        authority = self.receipt["write_authority"]
        self.assertEqual(
            handover["prior_snapshot_sha256"],
            handover["capsule_capture_snapshot_sha256"],
        )
        self.assertEqual(authority["before_snapshot_sha256"], handover["prior_snapshot_sha256"])
        self.assertEqual(authority["after_snapshot_sha256"], self.receipt["durable_reconciliation"]["snapshot_sha256"])
        self.assertNotEqual(handover["prior_target_sha256"], handover["replacement_target_sha256"])
        self.assertTrue(handover["prior_actor_quiescence_consumed_exactly_once"])
        self.assertEqual(authority["assignment_mutation_mode"], "write")
        self.assertEqual(authority["parent_recorded_user_write_intent"], "allow")
        self.assertEqual(authority["owned_paths"], ["qualified.txt"])
        self.assertEqual(authority["excluded_paths"], [])
        self.assertFalse(any(authority["git_authority"].values()))
        self.assertTrue(authority["writer_claim_absent_after_tool"])

    def test_identity_hook_callback_and_one_write_join(self):
        identity = self.receipt["identity"]
        authority = self.receipt["write_authority"]
        events = self.receipt["hook_binding"]["events"]
        self.assertEqual(identity["parent_thread_id"], identity["runtime_session_id"])
        self.assertEqual(
            identity["canonical_agent_path"],
            f"/root/{identity['requested_task_name']}",
        )
        self.assertEqual([event["sequence"] for event in events], list(range(2819, 2824)))
        self.assertEqual(
            [(event["hook_event_name"], event["scope"]) for event in events],
            [
                ("PreToolUse", "target_spawn"),
                ("SubagentStart", "target_child"),
                ("PreToolUse", "target_child"),
                ("PostToolUse", "target_child"),
                ("SubagentStop", "target_child"),
            ],
        )
        self.assertEqual(events[2]["tool_use_id"], authority["tool_use_id"])
        self.assertEqual(events[3]["tool_use_id"], authority["tool_use_id"])
        self.assertTrue(self.receipt["accepted_report"]["callback_payload_byte_identical_to_child_final"])
        self.assertFalse(self.receipt["accepted_report"]["wait_timed_out"])
        self.assertEqual(self.receipt["native_lifecycle"]["child_tool_call_count"], 1)

    def test_cleanup_close_is_not_mislabeled_as_running_actor_termination(self):
        lifecycle = self.receipt["native_lifecycle"]
        verdict = self.receipt["verdict"]
        self.assertEqual(lifecycle["close_mode"], "completed_cleanup_close")
        self.assertEqual(lifecycle["previous_status_kind"], "completed")
        self.assertEqual(
            lifecycle["previous_status_final_sha256"],
            self.receipt["accepted_report"]["child_final_sha256"],
        )
        self.assertFalse(lifecycle["child_second_turn_started"])
        self.assertFalse(lifecycle["child_turn_aborted"])
        self.assertTrue(lifecycle["session_loop_terminated"])
        self.assertTrue(lifecycle["tracked_process_maps_empty_for_exact_child"])
        self.assertTrue(lifecycle["tracked_process_termination_confirmed"])
        self.assertTrue(lifecycle["closed_catalog_actor_quiescence_claimed"])
        self.assertFalse(lifecycle["process_tree_quiescence_claimed"])
        self.assertTrue(verdict["completed_actor_cleanup_close_qualified_for_this_run"])
        self.assertFalse(verdict["resumed_running_actor_close_qualified_by_this_run"])

    def test_new_barrier_preserves_replacement_bytes_without_global_overclaim(self):
        reconciliation = self.receipt["durable_reconciliation"]
        observations = self.receipt["post_termination_barrier"]["observations"]
        self.assertEqual(reconciliation["pre_reconciliation_bucket"], "reported")
        self.assertEqual(reconciliation["post_reconciliation_bucket"], "unresolved")
        self.assertEqual(reconciliation["host_guarantee"], "child_terminated_and_mutations_quiesced")
        self.assertEqual(len(observations), 2)
        for field in ("head", "git_status_short", "snapshot_sha256", "target_sha256"):
            self.assertEqual(observations[0][field], observations[1][field])
        self.assertTrue(all(item["candidate_process_absent"] for item in observations))
        self.assertFalse(self.receipt["post_termination_barrier"]["late_write_observed"])
        self.assertFalse(reconciliation["process_tree_quiescence_claimed"])

    def test_status_and_phase_remain_fail_closed(self):
        verdict = self.receipt["verdict"]
        self.assertTrue(verdict["exact_prior_quiescence_handover_consumed_for_this_run"])
        self.assertTrue(verdict["replacement_exact_path_write_qualified_for_this_run"])
        self.assertFalse(verdict["before_mid_after_handover_races_qualified"])
        self.assertFalse(verdict["strong_global_process_tree_quiescence_qualified"])
        self.assertFalse(verdict["all_mutation_surfaces_qualified"])
        self.assertEqual(verdict["p5b_state"], "partial")
        self.assertFalse(verdict["phase1_complete"])
        self.assertFalse(verdict["direct_write_qualified"])
        p5b = next(gate for gate in self.status["phase1"]["gates"] if gate["id"] == "P5b")
        self.assertIn(RECEIPT.relative_to(ROOT).as_posix(), p5b["evidence"])
        self.assertEqual(p5b["state"], "partial")
        self.assertFalse(self.status["phase1"]["declared_complete"])
        self.assertFalse(self.status["phase1"]["declared_direct_write_qualified"])


if __name__ == "__main__":
    unittest.main()
