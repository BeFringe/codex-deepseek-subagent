import hashlib
import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
PROBE_PATH = ROOT / "probes" / "g4-live-nested-identity-20260908.json"
INPUT_PATH = (
    ROOT
    / "probes"
    / "g4-live-nested-identity-parent-adjudication-input-20260908.json"
)
RESULT_PATH = (
    ROOT
    / "probes"
    / "g4-live-nested-identity-parent-adjudication-result-20260908.json"
)
STATUS_PATH = ROOT / "probes" / "phase1-g4-status.json"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class LiveNestedIdentityEvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.probe = json.loads(PROBE_PATH.read_text(encoding="utf-8"))
        cls.input = json.loads(INPUT_PATH.read_text(encoding="utf-8"))
        cls.result = json.loads(RESULT_PATH.read_text(encoding="utf-8"))

    def test_frozen_probe_and_adjudication_hashes_are_exact(self) -> None:
        self.assertEqual(self.input["source_probe"]["sha256"], sha256(PROBE_PATH))
        self.assertEqual(self.result["input_evidence"]["sha256"], sha256(INPUT_PATH))
        self.assertEqual(
            self.result["parent_adjudication"]["evidence_sha256"],
            sha256(INPUT_PATH),
        )

    def test_three_sessionmeta_identities_form_exact_depth_two_chain(self) -> None:
        live = self.probe["live_probe"]
        root = live["root_parent"]
        outer = live["outer_scout"]
        inner = live["inner_child"]

        self.assertEqual(root["canonical_agent_path"], "/root")
        self.assertEqual(outer["parent_thread_id"], root["thread_id"])
        self.assertEqual(inner["parent_thread_id"], outer["thread_id"])
        self.assertEqual(outer["depth"], 1)
        self.assertEqual(inner["depth"], 2)
        self.assertEqual(
            outer["canonical_agent_path"],
            f"/root/{outer['requested_task_name']}",
        )
        self.assertEqual(
            inner["canonical_agent_path"],
            f"{outer['canonical_agent_path']}/{inner['requested_task_name']}",
        )
        self.assertEqual(outer["runtime_session_id"], root["runtime_session_id"])
        self.assertEqual(inner["runtime_session_id"], root["runtime_session_id"])
        self.assertEqual(outer["agent_type"], "explorer")
        self.assertEqual(inner["agent_type"], "g4_qualification_probe_worker")
        self.assertTrue(outer["sessionmeta_identity_exact"])
        self.assertTrue(inner["sessionmeta_identity_exact"])

        edges = live["identity_edges"]
        self.assertEqual(len(edges), 2)
        self.assertTrue(all(edge["sessionmeta_direct_parent_exact"] for edge in edges))
        self.assertEqual(edges[0]["child_thread_id"], outer["thread_id"])
        self.assertEqual(edges[1]["parent_thread_id"], outer["thread_id"])
        self.assertEqual(edges[1]["child_thread_id"], inner["thread_id"])

    def test_nested_assignment_is_bound_once_and_worker_stays_read_only(self) -> None:
        live = self.probe["live_probe"]
        outer = live["outer_scout"]
        inner = live["inner_child"]
        self.assertEqual(outer["requested_fork_turns"], "none")
        self.assertEqual(outer["authority_envelope_begin_count"], 1)
        self.assertEqual(outer["authority_envelope_end_count"], 1)
        self.assertEqual(outer["inner_assignment_sha256"], inner["assignment_sha256"])
        self.assertEqual(inner["assignment_mutation_mode"], "read_only")
        self.assertEqual(inner["native_tool_name"], "list_agents")
        self.assertEqual(inner["native_tool_call_count"], 1)
        self.assertEqual(inner["other_tool_call_count"], 0)
        self.assertEqual(outer["mutation_tools_called"], [])
        self.assertEqual(inner["final_attestation"]["changed_paths"], [])
        self.assertFalse(inner["final_attestation"]["authority_violation"])
        self.assertEqual(
            inner["native_tool_result_agent_paths"],
            [
                "/root",
                "/root/g4_nested_parent_2",
                "/root/g4_nested_parent_2/g4_nested_identity_2",
            ],
        )
        self.assertTrue(inner["native_tool_result_all_running"])

    def test_hook_chain_joins_nested_spawn_start_tool_and_corrected_stop(self) -> None:
        hook = self.probe["live_probe"]["hook_event_chain"]
        self.assertEqual(hook["event_count"], 5)
        self.assertEqual(hook["sequence_end"] - hook["sequence_start"] + 1, 5)
        self.assertEqual(
            [event["hook_event_name"] for event in hook["events"]],
            [
                "PreToolUse",
                "SubagentStart",
                "PreToolUse",
                "SubagentStop",
                "SubagentStop",
            ],
        )
        self.assertEqual(hook["events"][0]["scope"], "target_spawn")
        self.assertEqual(
            hook["events"][0]["canonical_agent_path"],
            "/root/g4_nested_parent_2",
        )
        self.assertEqual(
            hook["events"][1]["canonical_agent_path"],
            "/root/g4_nested_parent_2/g4_nested_identity_2",
        )
        self.assertEqual(hook["events"][2]["tool_name"], "g4_assignmentlist_agents")
        self.assertEqual(hook["events"][3]["result"], "correction_required")
        self.assertEqual(hook["events"][4]["result"], "reported")
        self.assertFalse(hook["raw_payload_stored"])

    def test_final_correction_callbacks_and_exit_are_adjudicated(self) -> None:
        live = self.probe["live_probe"]
        inner = live["inner_child"]
        expected_callback = (
            "NESTED.PARENT.CALLBACK outer=/root/g4_nested_parent_2 "
            "inner=/root/g4_nested_parent_2/g4_nested_identity_2"
        )
        self.assertEqual(inner["subagent_stop_observation_count"], 2)
        self.assertEqual(inner["correction_prompt_count"], 1)
        self.assertEqual(
            inner["first_stop_result"],
            "TASK.FINAL_INVALID_FINAL_WITHOUT_CONTRIBUTION",
        )
        self.assertTrue(inner["final_attestation_exact"])
        self.assertEqual(live["outer_scout"]["terminal_callback_exact"], expected_callback)
        self.assertEqual(live["root_parent"]["terminal_callback_exact"], expected_callback)
        self.assertEqual(live["headless_harness"]["candidate_exit_code"], 0)
        verdict = self.result["scope_verdict"]
        self.assertTrue(verdict["subagentstop_correction_adjudicated"])
        self.assertTrue(verdict["outer_and_root_terminal_callbacks_adjudicated"])

    def test_fresh_owner_consumed_only_after_all_five_dimensions_pass(self) -> None:
        self.assertEqual(
            set(self.input["adjudication_input"].values()),
            {"pass"},
        )
        transition = self.result["transition"]
        self.assertEqual(transition["source"], "reported")
        self.assertEqual(transition["destination"], "consumed")
        self.assertTrue(transition["consumed_present_after"])
        self.assertTrue(transition["active_absent_after"])
        self.assertTrue(transition["reported_absent_after"])
        self.assertTrue(transition["unresolved_absent_after"])
        self.assertEqual(
            self.input["nested_identity"]["inner"]["assignment_id"],
            transition["assignment_id"],
        )

    def test_barrier_and_scope_do_not_overclaim_phase_completion(self) -> None:
        barrier = self.result["post_transition_barrier"]
        self.assertEqual(barrier["head_tree"], barrier["write_tree"])
        self.assertTrue(barrier["only_parent_evidence_writes_present"])
        self.assertTrue(barrier["candidate_process_absent"])
        self.assertTrue(barrier["code_mode_host_process_absent"])
        self.assertFalse(barrier["strong_global_quiescence_claimed"])
        verdict = self.result["scope_verdict"]
        self.assertTrue(verdict["single_nested_identity_chain_qualified"])
        for field in (
            "nested_identity_cohort_complete",
            "mutation_contribution_adjudicated",
            "mutation_negative_space_complete",
            "strong_global_quiescence_complete",
            "windows_parity_complete",
            "representative_cost_or_latency_cohort_complete",
            "phase1_complete",
            "direct_write_qualified",
        ):
            self.assertFalse(verdict[field])
        self.assertEqual(verdict["phase2_state"], "closed")
        self.assertEqual(verdict["phase3_state"], "closed")
        verification = self.result["verification"]
        self.assertEqual(verification["provider_free_suite"]["test_count"], 606)
        self.assertEqual(verification["provider_free_suite"]["exit_code"], 0)
        self.assertEqual(
            verification["provider_free_suite"]["agent_template_checks"],
            "passed",
        )
        self.assertEqual(verification["phase1_gate"]["normal_exit_code"], 0)
        self.assertEqual(verification["phase1_gate"]["require_complete_exit_code"], 2)
        self.assertEqual(verification["mutation_matrix"]["blocker_count"], 13)
        self.assertEqual(verification["mutation_matrix"]["require_qualified_exit_code"], 2)
        self.assertFalse(verification["same_uid_trust"]["same_uid_rollout_protected"])
        self.assertFalse(verification["same_uid_trust"]["same_uid_state_protected"])
        self.assertEqual(
            verification["hook_event_chain"]["pending_tool_use_ids"],
            ["exec-04d901ca-1eb5-4ecf-a046-16440788c4d3"],
        )
        self.assertEqual(
            verification["hook_event_chain"]["require_complete_callbacks_exit_code"],
            2,
        )

    def test_status_cites_nested_result_without_qualifying_open_gates(self) -> None:
        status = json.loads(STATUS_PATH.read_text(encoding="utf-8"))
        gates = {gate["id"]: gate for gate in status["phase1"]["gates"]}
        result_path = (
            "probes/"
            "g4-live-nested-identity-parent-adjudication-result-20260908.json"
        )
        for gate_id in ("P1", "P2", "P3", "P6", "P6a", "P6b", "P7"):
            self.assertEqual(gates[gate_id]["state"], "partial")
            self.assertIn(result_path, gates[gate_id]["evidence"])
        self.assertFalse(status["phase1"]["declared_complete"])
        self.assertFalse(status["phase1"]["declared_direct_write_qualified"])

    def test_no_credential_value_or_name_is_stored(self) -> None:
        self.assertFalse(self.probe["runtime"]["credential_values_observed_or_recorded"])
        self.assertFalse(self.result["credential_values_stored"])
        combined = json.dumps(
            {"probe": self.probe, "input": self.input, "result": self.result},
            sort_keys=True,
        )
        self.assertNotIn("API_KEY", combined)


if __name__ == "__main__":
    unittest.main()
