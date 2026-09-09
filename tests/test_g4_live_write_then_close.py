import hashlib
import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
RECEIPT = ROOT / "probes" / "g4-live-write-then-close-20260909.json"
WRAPPER = ROOT / "probes" / "codex_plaintext_candidate_wrapper.sh"
RECONCILER = ROOT / "probes" / "reconcile_g4_write_then_close.py"


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


class G4LiveWriteThenCloseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.receipt = json.loads(RECEIPT.read_text(encoding="utf-8"))

    def test_guard_and_reconciler_are_hash_bound(self):
        self.assertEqual(self.receipt["probe_guard"]["wrapper_sha256"], sha256(WRAPPER))
        self.assertEqual(
            self.receipt["durable_reconciliation"]["tool_sha256"],
            sha256(RECONCILER),
        )
        self.assertEqual(
            self.receipt["probe_guard"]["authorization"],
            "CODEX_G4_P5B_TRACKED_TERMINATION_PROBE_AUTHORIZED="
            "schema1-exact-write-then-close",
        )
        self.assertEqual(
            self.receipt["probe_guard"]["fixed_temporary_namespace"],
            "/private/tmp/codex-g4-p5b-write-termination.*",
        )
        self.assertFalse(self.receipt["runtime"]["gui_app_server_selected"])
        self.assertFalse(self.receipt["runtime"]["credential_value_observed"])

    def test_exact_identity_write_ceiling_and_receipt_are_frozen(self):
        identity = self.receipt["identity"]
        authority = self.receipt["write_authority"]
        self.assertEqual(identity["parent_thread_id"], identity["runtime_session_id"])
        self.assertEqual(
            identity["canonical_agent_path"],
            f"/root/{identity['requested_task_name']}",
        )
        self.assertEqual(authority["assignment_mutation_mode"], "write")
        self.assertEqual(authority["parent_recorded_user_write_intent"], "allow")
        self.assertEqual(authority["trusted_host_user_write_consent_status"], "verified")
        self.assertEqual(authority["owned_paths"], ["qualified.txt"])
        self.assertEqual(authority["excluded_paths"], [])
        self.assertFalse(any(authority["git_authority"].values()))
        self.assertEqual(authority["tool_name"], "apply_patch")
        self.assertEqual(authority["target_size_bytes"], 25)
        self.assertTrue(authority["writer_claim_absent_after_tool"])

    def test_hook_chain_and_accepted_callback_bind_the_same_write(self):
        hook = self.receipt["hook_binding"]
        authority = self.receipt["write_authority"]
        self.assertEqual(
            [(event["hook_event_name"], event["scope"]) for event in hook["events"]],
            [
                ("PreToolUse", "target_spawn"),
                ("SubagentStart", "target_child"),
                ("PreToolUse", "target_child"),
                ("PostToolUse", "target_child"),
                ("SubagentStop", "target_child"),
            ],
        )
        self.assertEqual([event["sequence"] for event in hook["events"]], list(range(2720, 2725)))
        self.assertTrue(hook["contiguous"])
        self.assertTrue(hook["accepted_subagentstop_present"])
        self.assertEqual(hook["events"][2]["tool_use_id"], authority["tool_use_id"])
        self.assertEqual(hook["events"][3]["tool_use_id"], authority["tool_use_id"])
        accepted = self.receipt["accepted_report"]
        self.assertTrue(accepted["callback_payload_byte_identical_to_child_final"])
        self.assertFalse(accepted["wait_timed_out"])
        self.assertTrue(accepted["reported_before_termination"])

    def test_resumed_child_close_receipt_is_exact_and_bounded(self):
        identity = self.receipt["identity"]
        lifecycle = self.receipt["native_lifecycle"]
        close = lifecycle["close_receipt"]
        child = identity["child_thread_id"]
        empty = {child: []}
        self.assertEqual(close["previous_status"], "running")
        self.assertEqual(close["target_thread_id"], child)
        self.assertEqual(close["target_agent_path"], identity["canonical_agent_path"])
        self.assertTrue(close["session_loop_terminated"])
        self.assertTrue(close["model_callable_process_bootstrap_absent"])
        self.assertEqual(close["tracked_background_processes_before_close"], 0)
        for field in (
            "tracked_process_ids_by_thread",
            "confirmed_exit_process_ids_by_thread",
            "unconfirmed_exit_process_ids_by_thread",
            "unresolved_start_process_ids_by_thread",
        ):
            self.assertEqual(close[field], empty)
        self.assertTrue(close["tracked_process_termination_confirmed"])
        self.assertTrue(close["closed_catalog_actor_quiescence_claimed"])
        self.assertFalse(close["process_tree_quiescence_claimed"])
        self.assertEqual(lifecycle["close_receipt_sha256"], canonical_sha256(close))
        self.assertEqual(lifecycle["second_turn_tool_call_count"], 0)
        self.assertEqual(lifecycle["second_turn_assistant_final_count"], 0)
        self.assertTrue(lifecycle["target_absent_from_post_close_tree"])

    def test_durable_barrier_preserves_the_accepted_dirty_bytes(self):
        reconciliation = self.receipt["durable_reconciliation"]
        self.assertEqual(reconciliation["pre_reconciliation_bucket"], "reported")
        self.assertEqual(reconciliation["post_reconciliation_bucket"], "unresolved")
        self.assertEqual(
            reconciliation["host_guarantee"],
            "child_terminated_and_mutations_quiesced",
        )
        self.assertFalse(reconciliation["process_tree_quiescence_claimed"])
        observations = self.receipt["post_termination_barrier"]["observations"]
        self.assertEqual(len(observations), 2)
        for field in ("head", "tree", "git_status_short", "target_sha256"):
            self.assertEqual(observations[0][field], observations[1][field])
        self.assertEqual(observations[0]["git_status_short"], "?? qualified.txt")
        self.assertEqual(observations[0]["candidate_open_file_count"], 0)
        self.assertEqual(observations[1]["candidate_open_file_count"], 0)
        self.assertFalse(self.receipt["post_termination_barrier"]["late_write_observed"])

    def test_scope_is_one_run_and_phase_remains_closed(self):
        verdict = self.receipt["verdict"]
        self.assertTrue(verdict["exact_mutation_actor_session_termination_qualified_for_this_run"])
        self.assertTrue(verdict["accepted_report_before_close_qualified_for_this_run"])
        self.assertTrue(verdict["exact_writer_receipt_qualified_for_this_run"])
        self.assertTrue(
            verdict[
                "exact_mutation_actor_post_termination_disk_barrier_qualified_for_this_run"
            ]
        )
        self.assertFalse(verdict["detached_or_untracked_process_quiescence_qualified"])
        self.assertFalse(verdict["strong_global_process_tree_quiescence_qualified"])
        self.assertFalse(verdict["ownership_handover_races_qualified"])
        self.assertEqual(verdict["p5b_state"], "partial")
        self.assertFalse(verdict["phase1_complete"])
        self.assertFalse(verdict["direct_write_qualified"])
        self.assertEqual(verdict["phase2_state"], "closed")
        self.assertEqual(verdict["phase3_state"], "closed")


if __name__ == "__main__":
    unittest.main()
