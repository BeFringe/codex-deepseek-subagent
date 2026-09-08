import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
RECORD = ROOT / "probes" / "g4-live-session-close-20260908.json"
STATUS = ROOT / "probes" / "phase1-g4-status.json"


class G4LiveSessionCloseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.record = json.loads(RECORD.read_text(encoding="utf-8"))
        cls.status = json.loads(STATUS.read_text(encoding="utf-8"))

    def test_parent_child_identity_is_exact_across_sessionmeta_and_close(self):
        parent = self.record["parent"]
        child = self.record["child"]
        close = self.record["host_session_close_receipt"]
        transport = self.record["transport"]

        self.assertEqual(parent["thread_id"], parent["runtime_session_id"])
        self.assertEqual(child["runtime_session_id"], parent["thread_id"])
        self.assertEqual(child["parent_thread_id"], parent["thread_id"])
        self.assertEqual(close["target_thread_id"], child["thread_id"])
        self.assertEqual(close["target_agent_path"], child["canonical_agent_path"])
        self.assertEqual(
            transport["canonical_agent_path"], child["canonical_agent_path"]
        )
        self.assertEqual(transport["requested_task_name"], "g4_session_close_4")
        self.assertEqual(transport["authority_begin_count"], 1)
        self.assertEqual(transport["authority_end_count"], 1)

    def test_close_observed_running_child_and_waited_for_session_loop(self):
        close = self.record["host_session_close_receipt"]
        child = self.record["child"]
        after = self.record["post_close_host_observation"]

        self.assertEqual(close["previous_status"], "running")
        self.assertTrue(close["session_loop_terminated"])
        self.assertLess(child["turn_aborted_at"], close["returned_at"])
        self.assertEqual(close["child_turn_aborted_before_receipt_ms"], 255)
        self.assertTrue(after["target_absent_from_live_tree"])
        self.assertEqual(after["agents"], [{"agent_name": "/root", "agent_status": "running"}])
        self.assertTrue(after["candidate_process_absent_after_parent_exit"])

    def test_child_never_mutated_or_returned_an_accepted_contribution(self):
        child = self.record["child"]
        disk = self.record["post_close_disk_barrier"]
        authority = self.record["authority"]

        self.assertEqual(child["native_tool_call_count"], 0)
        self.assertEqual(child["subagent_stop_block_count"], 3)
        self.assertFalse(child["accepted_final_observed"])
        self.assertFalse(child["task_complete_observed"])
        self.assertEqual(authority["assignment_mutation_mode"], "read_only")
        self.assertEqual(authority["owned_paths"], [])
        self.assertEqual(disk["git_status_short"], "")
        self.assertEqual(disk["changed_paths"], [])
        self.assertFalse(disk["disk_changed"])

    def test_hook_chain_is_exact_and_omits_raw_payload(self):
        chain = self.record["hook_event_chain_snapshot"]
        events = chain["target_events"]

        self.assertEqual(chain["event_count"], 1638)
        self.assertEqual([item["sequence"] for item in events], list(range(1634, 1639)))
        self.assertEqual(events[0]["hook_event_name"], "PreToolUse")
        self.assertEqual(events[1]["hook_event_name"], "SubagentStart")
        self.assertTrue(
            all(item["hook_event_name"] == "SubagentStop" for item in events[2:])
        )
        self.assertFalse(chain["raw_payload_stored"])

    def test_failed_preflights_are_recorded_without_false_close_receipts(self):
        attempts = self.record["preflight_attempts"]

        self.assertEqual(len(attempts), 3)
        self.assertEqual(
            [item["result"] for item in attempts],
            ["stopped_before_close", "stopped_before_close", "stopped_before_spawn"],
        )
        self.assertTrue(all(not item["close_receipt_claimed"] for item in attempts))
        self.assertTrue(all("parent_rollout_sha256" in item for item in attempts))

    def test_session_close_does_not_become_mutation_quiescence_or_handover(self):
        close = self.record["host_session_close_receipt"]
        boundary = self.record["source_boundary"]
        authority = self.record["authority"]
        verdict = self.record["verdict"]

        self.assertFalse(close["process_tree_quiescence_claimed"])
        self.assertFalse(close["mutation_quiescence_claimed"])
        self.assertFalse(boundary["tracked_unified_exec_termination_is_confirmed_exit_barrier"])
        self.assertFalse(boundary["detached_or_untracked_descendants_covered"])
        self.assertFalse(boundary["closed_mutation_surface_proven_live"])
        self.assertFalse(boundary["zero_inflight_writer_claims_for_target_proven"])
        self.assertEqual(authority["state_after_outer_owner_reconciliation"], "unresolved")
        self.assertFalse(authority["quiescence_barrier_written"])
        self.assertFalse(authority["ownership_handover_authorized"])
        self.assertTrue(verdict["native_host_session_termination_primitive_qualified"])
        self.assertFalse(verdict["p5b_strong_termination_mutation_quiescence_qualified"])
        self.assertFalse(verdict["ownership_handover_qualified"])
        self.assertFalse(verdict["phase1_complete"])
        self.assertFalse(verdict["direct_write_qualified"])
        self.assertEqual(verdict["phase2_state"], "closed")
        self.assertEqual(verdict["phase3_state"], "closed")

    def test_status_keeps_p5b_and_termination_receipt_partial(self):
        phase1 = self.status["phase1"]
        p5b = next(row for row in phase1["gates"] if row["id"] == "P5b")
        termination = next(
            row
            for row in phase1["exit_receipts"]
            if row["id"] == "termination_quiescence"
        )

        for row in (p5b, termination):
            self.assertEqual(row["state"], "partial")
            self.assertIn("probes/g4-live-session-close-20260908.json", row["evidence"])
            self.assertIn("tests/test_g4_live_session_close.py", row["evidence"])
        self.assertFalse(phase1["declared_complete"])
        self.assertFalse(phase1["declared_direct_write_qualified"])


if __name__ == "__main__":
    unittest.main()
