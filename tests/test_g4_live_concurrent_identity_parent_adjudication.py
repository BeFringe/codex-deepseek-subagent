from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]
INPUT_PATH = (
    ROOT
    / "probes"
    / "g4-live-concurrent-identity-parent-adjudication-input-20260908.json"
)
RESULT_PATH = (
    ROOT
    / "probes"
    / "g4-live-concurrent-identity-parent-adjudication-result-20260908.json"
)
SOURCE_PATH = ROOT / "probes" / "g4-live-concurrent-identity-20260908.json"
STATUS_PATH = ROOT / "probes" / "phase1-g4-status.json"
SHA256 = re.compile(r"^[0-9a-f]{64}$")


class G4LiveConcurrentIdentityParentAdjudicationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.input = json.loads(INPUT_PATH.read_text(encoding="utf-8"))
        cls.result = json.loads(RESULT_PATH.read_text(encoding="utf-8"))

    def test_result_hash_binds_the_exact_fresh_owner_input(self) -> None:
        digest = hashlib.sha256(INPUT_PATH.read_bytes()).hexdigest()
        self.assertEqual(self.result["input_evidence"]["sha256"], digest)
        self.assertEqual(self.result["parent_adjudication"]["evidence_sha256"], digest)
        self.assertRegex(digest, SHA256)

    def test_input_hash_binds_the_exact_live_source_receipt(self) -> None:
        digest = hashlib.sha256(SOURCE_PATH.read_bytes()).hexdigest()
        self.assertEqual(self.input["source_probe"]["sha256"], digest)
        self.assertRegex(digest, SHA256)

    def test_both_reported_records_transition_to_consumed(self) -> None:
        transitions = self.result["transitions"]
        self.assertEqual([item["concurrent_position"] for item in transitions], ["A", "B"])
        self.assertEqual(
            {item["assignment_id"] for item in transitions},
            {item["assignment_id"] for item in self.input["assignments"]},
        )
        for transition in transitions:
            self.assertEqual(
                (transition["source"], transition["destination"]),
                ("reported", "consumed"),
            )
            self.assertTrue(transition["active_absent_after"])
            self.assertTrue(transition["reported_absent_after"])
            self.assertTrue(transition["unresolved_absent_after"])
            self.assertTrue(transition["consumed_present_after"])
            self.assertRegex(transition["consumed_envelope_sha256"], SHA256)

    def test_five_parent_integrity_dimensions_are_exact_and_pass(self) -> None:
        expected = {
            "location_integrity",
            "mutation_scope_integrity",
            "verification_freshness",
            "derivation_provenance_integrity",
            "feasibility_contract_integrity",
        }
        adjudication = self.result["parent_adjudication"]
        self.assertEqual(set(adjudication) - {"evidence_sha256"}, expected)
        self.assertEqual(set(self.input["adjudication_input"]), expected)
        for field in expected:
            self.assertEqual(self.input["adjudication_input"][field], "pass")
            self.assertEqual(adjudication[field], "pass")

    def test_exact_concurrent_identities_and_read_only_frontier_are_distinct(self) -> None:
        first, second = self.input["assignments"]
        parent = self.input["fresh_parent_git_frontier_before_evidence_write"]
        worker = self.input["worker_git_frontier"]
        self.assertTrue(parent["worker_head_is_ancestor"])
        self.assertNotEqual(worker["head"], parent["head"])
        self.assertEqual(
            parent["changes_since_worker_head_owner"],
            "fresh_parent_phase1_evidence_and_acceptance_wording_only",
        )
        for field in (
            "assignment_id",
            "handoff_id",
            "requested_task_name",
            "canonical_agent_path",
            "child_thread_id",
            "child_turn_id",
            "assignment_sha256",
            "capsule_sha256",
            "compact_invariant_sha256",
        ):
            self.assertNotEqual(first[field], second[field])
        for assignment in (first, second):
            self.assertEqual(assignment["assignment_mutation_mode"], "read_only")
            self.assertEqual(assignment["changed_paths"], [])
            self.assertFalse(assignment["authority_violation"])
            self.assertTrue(assignment["assigned_slice_complete"])

    def test_actual_overlap_is_fresh_owner_adjudicated(self) -> None:
        lifecycle = self.input["concurrent_lifecycle"]
        self.assertTrue(lifecycle["child_b_start_before_child_a_accepted_stop"])
        self.assertTrue(lifecycle["child_b_list_observed_both_children_running"])
        self.assertTrue(lifecycle["actual_child_execution_overlap_observed"])
        self.assertGreater(lifecycle["observed_overlap_until_child_a_accepted_stop_ms"], 0)
        self.assertTrue(lifecycle["both_parent_callbacks_observed"])
        self.assertTrue(self.result["scope_verdict"]["actual_execution_overlap_adjudicated"])

    def test_parent_projection_gap_remains_separate_from_fresh_owner_authority(self) -> None:
        projection = self.input["parent_projection"]
        self.assertTrue(projection["source_parent_declared_failure"])
        self.assertFalse(projection["spawn_results_exposed_child_thread_ids"])
        self.assertFalse(projection["wait_results_exposed_child_thread_ids"])
        self.assertFalse(projection["source_parent_self_adjudication_complete"])
        self.assertTrue(projection["fresh_owner_sessionmeta_hook_join_complete"])
        self.assertFalse(self.result["scope_verdict"]["parent_projection_complete"])

    def test_consumption_does_not_overclaim_cohort_or_phase_completion(self) -> None:
        barrier = self.result["post_transition_barrier"]
        verdict = self.result["scope_verdict"]
        self.assertTrue(barrier["candidate_process_absent"])
        self.assertTrue(barrier["headless_candidate_exit_code_observed"])
        self.assertEqual(barrier["headless_candidate_exit_code"], 0)
        self.assertFalse(barrier["strong_global_quiescence_claimed"])
        self.assertTrue(verdict["provider_free_concurrent_identity_pair_consumed"])
        for field in (
            "parent_projection_complete",
            "identity_cohort_complete",
            "nested_identity_complete",
            "concurrent_identity_cohort_complete",
            "resume_identity_complete",
            "mutation_contribution_adjudicated",
            "mutation_negative_space_complete",
            "strong_global_quiescence_complete",
            "representative_cost_or_latency_cohort_complete",
            "phase1_complete",
            "direct_write_qualified",
        ):
            self.assertFalse(verdict[field])
        self.assertEqual(verdict["phase2_state"], "closed")
        self.assertEqual(verdict["phase3_state"], "closed")
        self.assertFalse(self.result["credential_values_stored"])

    def test_status_accumulates_this_receipt_without_opening_phase1(self) -> None:
        status = json.loads(STATUS_PATH.read_text(encoding="utf-8"))
        gates = {gate["id"]: gate for gate in status["phase1"]["gates"]}
        result_path = (
            "probes/"
            "g4-live-concurrent-identity-parent-adjudication-result-20260908.json"
        )
        self.assertEqual(gates["P1"]["state"], "qualified")
        self.assertIn(result_path, gates["P1"]["evidence"])
        for gate_id in ("P2", "P3", "P6", "P6a", "P6b"):
            self.assertIn(result_path, gates[gate_id]["evidence"])
        for gate_id in ("P2", "P3", "P6", "P6a", "P6b"):
            self.assertEqual(gates[gate_id]["state"], "qualified")
        self.assertTrue(status["phase1"]["declared_complete"])
        self.assertTrue(status["phase1"]["declared_direct_write_qualified"])

    def test_fresh_provider_free_and_fail_closed_exit_results_are_exact(self) -> None:
        verification = self.result["verification"]
        suite = verification["provider_free_suite"]
        self.assertEqual(suite["test_count"], 495)
        self.assertEqual(suite["duration_seconds"], 56.504)
        self.assertEqual(suite["exit_code"], 0)
        self.assertEqual(suite["agent_template_checks"], "passed")
        self.assertEqual(verification["phase1_gate_normal_exit_code"], 0)
        self.assertEqual(verification["phase1_gate_require_complete_exit_code"], 2)
        self.assertEqual(verification["mutation_matrix_normal_exit_code"], 0)
        self.assertEqual(verification["mutation_matrix_blocker_count"], 13)
        self.assertEqual(verification["mutation_matrix_require_qualified_exit_code"], 2)
        self.assertEqual(verification["same_uid_probe_exit_code"], 0)
        self.assertEqual(verification["same_uid_require_protected_exit_code"], 2)
        self.assertFalse(verification["same_uid_rollout_protected"])
        self.assertFalse(verification["same_uid_state_protected"])


if __name__ == "__main__":
    unittest.main()
