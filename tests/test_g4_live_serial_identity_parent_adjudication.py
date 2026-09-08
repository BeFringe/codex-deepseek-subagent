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
    / "g4-live-serial-identity-parent-adjudication-input-20260908.json"
)
RESULT_PATH = (
    ROOT
    / "probes"
    / "g4-live-serial-identity-parent-adjudication-result-20260908.json"
)
STATUS_PATH = ROOT / "probes" / "phase1-g4-status.json"
SHA256 = re.compile(r"^[0-9a-f]{64}$")


class G4LiveSerialIdentityParentAdjudicationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.input = json.loads(INPUT_PATH.read_text(encoding="utf-8"))
        cls.result = json.loads(RESULT_PATH.read_text(encoding="utf-8"))

    def test_result_hash_binds_the_exact_fresh_owner_input(self) -> None:
        digest = hashlib.sha256(INPUT_PATH.read_bytes()).hexdigest()
        self.assertEqual(self.result["input_evidence"]["sha256"], digest)
        self.assertEqual(self.result["parent_adjudication"]["evidence_sha256"], digest)
        self.assertTrue(SHA256.fullmatch(digest))

    def test_both_reported_records_transition_to_consumed(self) -> None:
        transitions = self.result["transitions"]
        self.assertEqual(len(transitions), 2)
        self.assertEqual([item["serial_position"] for item in transitions], ["A", "B"])
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
            self.assertTrue(SHA256.fullmatch(transition["consumed_envelope_sha256"]))

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

    def test_exact_serial_identities_remain_distinct(self) -> None:
        first, second = self.input["assignments"]
        source_parent = self.input["source_parent_identity"]
        fresh_parent = self.input["parent_identity"]
        self.assertEqual(source_parent["canonical_agent_path"], "/root")
        self.assertEqual(fresh_parent["canonical_agent_path"], "/root")
        self.assertEqual(fresh_parent["adjudication_authority"], "fresh_owner")
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

    def test_read_only_worker_frontier_is_separate_from_parent_evidence_commits(self) -> None:
        worker = self.input["worker_git_frontier"]
        parent = self.input["fresh_parent_git_frontier_before_evidence_write"]
        self.assertTrue(parent["worker_head_is_ancestor"])
        self.assertNotEqual(worker["head"], parent["head"])
        self.assertEqual(
            parent["changes_since_worker_head"],
            [
                "docs/phase1-evidence.md",
                "probes/g4-live-serial-identity-20260908.json",
                "probes/phase1-g4-status.json",
                "tests/test_g4_live_serial_identity.py",
            ],
        )
        self.assertEqual(
            parent["changes_since_worker_head_owner"],
            "fresh_parent_evidence_only",
        )
        for assignment in self.input["assignments"]:
            self.assertEqual(assignment["assignment_mutation_mode"], "read_only")
            self.assertEqual(assignment["changed_paths"], [])
            self.assertFalse(assignment["authority_violation"])
            self.assertTrue(assignment["assigned_slice_complete"])

    def test_serial_callback_and_final_correction_are_adjudicated(self) -> None:
        lifecycle = self.input["serial_lifecycle"]
        first, second = self.input["assignments"]
        self.assertTrue(lifecycle["child_b_spawn_after_child_a_callback"])
        self.assertGreater(lifecycle["callback_to_next_spawn_gap_ms"], 0)
        self.assertFalse(lifecycle["overlapping_child_execution_observed"])
        self.assertTrue(lifecycle["both_parent_callbacks_observed"])
        self.assertEqual(first["final_correction_count"], 1)
        self.assertEqual(second["final_correction_count"], 0)
        self.assertTrue(self.result["scope_verdict"]["subagentstop_correction_adjudicated"])

    def test_consumption_does_not_overclaim_termination_or_phase_completion(self) -> None:
        barrier = self.result["post_transition_barrier"]
        verdict = self.result["scope_verdict"]
        self.assertTrue(barrier["candidate_process_absent"])
        self.assertFalse(barrier["headless_candidate_exit_code_observed"])
        self.assertFalse(barrier["strong_global_quiescence_claimed"])
        self.assertTrue(verdict["provider_free_serial_identity_pair_consumed"])
        for field in (
            "identity_cohort_complete",
            "nested_identity_complete",
            "concurrent_identity_complete",
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

    def test_status_keeps_required_gates_partial(self) -> None:
        status = json.loads(STATUS_PATH.read_text(encoding="utf-8"))
        gates = {gate["id"]: gate for gate in status["phase1"]["gates"]}
        result_path = (
            "probes/"
            "g4-live-serial-identity-parent-adjudication-result-20260908.json"
        )
        self.assertEqual(gates["P1"]["state"], "qualified")
        self.assertIn(result_path, gates["P1"]["evidence"])
        for gate_id in ("P2", "P3", "P6", "P6a", "P6b"):
            self.assertEqual(gates[gate_id]["state"], "partial")
            self.assertIn(result_path, gates[gate_id]["evidence"])
        self.assertFalse(status["phase1"]["declared_complete"])
        self.assertFalse(status["phase1"]["declared_direct_write_qualified"])

    def test_no_credential_value_or_name_is_stored(self) -> None:
        verification = self.result["verification"]
        suite = verification["provider_free_suite"]
        self.assertEqual(suite["test_count"], 468)
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
        self.assertFalse(self.input["runtime"]["credential_values_observed_or_recorded"])
        self.assertFalse(self.result["credential_values_stored"])
        combined = json.dumps(
            {"input": self.input, "result": self.result}, sort_keys=True
        )
        self.assertNotIn("API_KEY", combined)


if __name__ == "__main__":
    unittest.main()
