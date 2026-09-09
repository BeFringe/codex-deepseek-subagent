import hashlib
import json
from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]
SOURCE = (
    ROOT
    / "probes"
    / "current-signed-runtime-g4-p5b-tracked-termination-source-candidate.json"
)
PATCH = (
    ROOT
    / "probes"
    / "current-signed-runtime-g4-p5b-tracked-termination-source-candidate.patch"
)
RECEIPT = ROOT / "probes" / "g4-live-read-only-tracked-termination-20260909.json"
RECONCILER = ROOT / "probes" / "reconcile_g4_read_only_close.py"


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


class G4LiveReadOnlyTrackedTerminationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = json.loads(SOURCE.read_text(encoding="utf-8"))
        cls.receipt = json.loads(RECEIPT.read_text(encoding="utf-8"))

    def test_incremental_source_patch_is_hash_bound_and_narrow(self):
        reconstruction = self.source["reconstruction"]
        self.assertEqual(reconstruction["patch_sha256"], sha256(PATCH))
        self.assertEqual(reconstruction["changed_path_count"], 13)
        self.assertFalse(reconstruction["cargo_lock_included"])
        self.assertTrue(reconstruction["all_changed_paths_match_candidate_worktree"])
        changed = re.findall(
            r"^diff --git a/(.+?) b/",
            PATCH.read_text(encoding="utf-8"),
            flags=re.MULTILINE,
        )
        self.assertEqual(len(changed), len(set(changed)))
        self.assertEqual(len(changed), 13)
        self.assertIn("codex-rs/core/src/unified_exec/process.rs", changed)
        self.assertIn(
            "codex-rs/core/src/tools/handlers/multi_agents_v2/close_agent.rs",
            changed,
        )

    def test_close_receipt_has_exact_empty_process_maps(self):
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
        self.assertEqual(
            lifecycle["close_receipt_sha256"],
            canonical_sha256(close),
        )

    def test_real_sessionmeta_hook_binding_and_no_child_contribution_are_frozen(self):
        identity = self.receipt["identity"]
        hook = self.receipt["hook_binding"]
        self.assertEqual(identity["parent_thread_id"], identity["runtime_session_id"])
        self.assertEqual(
            identity["canonical_agent_path"],
            f"/root/{identity['requested_task_name']}",
        )
        self.assertEqual(
            [event["hook_event_name"] for event in hook["events"]],
            ["PreToolUse", "SubagentStart"],
        )
        self.assertEqual(
            [event["sequence"] for event in hook["events"]],
            [2669, 2670],
        )
        self.assertTrue(hook["contiguous"])
        self.assertEqual(hook["child_tool_call_count"], 0)
        self.assertEqual(hook["child_assistant_message_count"], 0)
        self.assertFalse(hook["accepted_subagentstop_present"])
        self.assertEqual(hook["child_turn_aborted_reason"], "interrupted")

    def test_durable_barrier_is_exact_and_does_not_overclaim_global_quiescence(self):
        reconciliation = self.receipt["durable_reconciliation"]
        self.assertEqual(reconciliation["tool_sha256"], sha256(RECONCILER))
        self.assertEqual(reconciliation["pre_reconciliation_bucket"], "active")
        self.assertEqual(reconciliation["post_reconciliation_bucket"], "unresolved")
        self.assertEqual(
            reconciliation["host_guarantee"],
            "child_terminated_and_mutations_quiesced",
        )
        self.assertFalse(reconciliation["process_tree_quiescence_claimed"])
        observations = self.receipt["post_termination_barrier"]["observations"]
        self.assertEqual(len(observations), 2)
        self.assertEqual(observations[0]["head"], observations[1]["head"])
        self.assertEqual(observations[0]["tree"], observations[1]["tree"])
        self.assertEqual(observations[0]["git_status_short"], "")
        self.assertEqual(observations[1]["git_status_short"], "")
        self.assertEqual(observations[0]["candidate_open_file_count"], 0)
        self.assertEqual(observations[1]["candidate_open_file_count"], 0)
        self.assertFalse(
            self.receipt["post_termination_barrier"][
                "strong_global_process_tree_quiescence_claimed"
            ]
        )

    def test_negative_attempts_are_not_promoted_and_phase_remains_closed(self):
        attempts = self.receipt["attempts"]
        self.assertFalse(attempts[0]["qualified"])
        self.assertFalse(attempts[1]["qualified"])
        self.assertTrue(attempts[2]["qualified"])
        verdict = self.receipt["verdict"]
        self.assertTrue(verdict["exact_read_only_actor_mutation_quiescence_qualified"])
        self.assertFalse(verdict["mutation_capable_actor_termination_qualified"])
        self.assertFalse(verdict["strong_global_process_tree_quiescence_qualified"])
        self.assertEqual(verdict["p5b_state"], "partial")
        self.assertFalse(verdict["phase1_complete"])
        self.assertFalse(verdict["direct_write_qualified"])
        self.assertEqual(verdict["phase2_state"], "closed")
        self.assertEqual(verdict["phase3_state"], "closed")


if __name__ == "__main__":
    unittest.main()
