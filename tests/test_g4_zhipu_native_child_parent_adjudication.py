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
    / "g4-zhipu-native-child-parent-adjudication-input-20260908.json"
)
RESULT_PATH = (
    ROOT
    / "probes"
    / "g4-zhipu-native-child-parent-adjudication-result-20260908.json"
)
RUNTIME_INDEX_PATH = ROOT / "probes" / "codex-runtime-evidence-index.json"
STATUS_PATH = ROOT / "probes" / "phase1-g4-status.json"
SHA256 = re.compile(r"^[0-9a-f]{64}$")


class G4ZhipuNativeChildParentAdjudicationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.input = json.loads(INPUT_PATH.read_text(encoding="utf-8"))
        cls.result = json.loads(RESULT_PATH.read_text(encoding="utf-8"))
        cls.runtime_index = json.loads(
            RUNTIME_INDEX_PATH.read_text(encoding="utf-8")
        )
        cls.status = json.loads(STATUS_PATH.read_text(encoding="utf-8"))

    def test_receipt_resolves_current_runtime_semantically(self) -> None:
        current_role = self.runtime_index["current_runtime_role"]
        current = self.runtime_index["runtime_roles"][current_role]

        self.assertEqual(self.input["runtime_role"], current_role)
        self.assertEqual(self.result["runtime_role"], current_role)
        self.assertEqual(self.input["runtime"]["codex_version"], current["codex_version"])
        self.assertEqual(
            self.input["runtime"]["base_source_commit"], current["source_commit"]
        )

    def test_result_hash_binds_exact_parent_input_and_consumed_transition(self) -> None:
        digest = hashlib.sha256(INPUT_PATH.read_bytes()).hexdigest()
        transition = self.result["transition"]
        adjudication = self.result["parent_adjudication"]

        self.assertEqual(self.result["input_evidence"]["sha256"], digest)
        self.assertEqual(adjudication["evidence_sha256"], digest)
        self.assertEqual(
            (transition["source"], transition["destination"]),
            ("reported", "consumed"),
        )
        for field in (
            "active_absent_after",
            "reported_absent_after",
            "unresolved_absent_after",
            "consumed_present_after",
        ):
            self.assertTrue(transition[field])
        self.assertRegex(transition["consumed_envelope_sha256"], SHA256)
        for field in (
            "location_integrity",
            "mutation_scope_integrity",
            "verification_freshness",
            "derivation_provenance_integrity",
            "feasibility_contract_integrity",
        ):
            self.assertEqual(adjudication[field], "pass")

    def test_exact_external_provider_identity_is_bound_without_spawn_override(self) -> None:
        runtime = self.input["runtime"]
        identity = self.input["identity"]
        sessionmeta = self.input["sessionmeta"]
        transport = self.input["assignment_transport"]

        self.assertEqual(runtime["parent_model_provider"], "openai")
        self.assertEqual(runtime["child_model_provider"], "zhipu")
        self.assertEqual(sessionmeta["root_model_provider"], "openai")
        self.assertEqual(sessionmeta["child_model_provider"], "zhipu")
        self.assertEqual(
            sessionmeta["child_source_parent_thread_id"], identity["parent_thread_id"]
        )
        self.assertEqual(
            sessionmeta["child_source_agent_path"], identity["canonical_agent_path"]
        )
        self.assertEqual(
            sessionmeta["child_source_agent_role"], identity["agent_type"]
        )
        self.assertEqual(
            transport["spawn_output_canonical_agent_path"],
            identity["canonical_agent_path"],
        )
        self.assertFalse(transport["model_override_present_in_spawn"])
        self.assertFalse(transport["reasoning_effort_override_present_in_spawn"])
        self.assertFalse(runtime["credential_values_observed_or_recorded"])

    def test_native_tool_call_and_hook_chain_join_exactly(self) -> None:
        tool = self.input["tool_loop"]
        chain = self.input["live_chain"]

        self.assertEqual(tool["name"], "list_agents")
        self.assertEqual(tool["namespace"], "g4_assignment")
        self.assertEqual(tool["function_output_status"], "success")
        self.assertRegex(tool["function_output_sha256"], SHA256)
        self.assertEqual((chain["sequence_start"], chain["sequence_end"]), (1175, 1179))
        self.assertEqual(chain["stop_attempts"], 2)
        for field in (
            "spawn_pretool_receipt_sha256",
            "subagent_start_receipt_sha256",
            "child_pretool_receipt_sha256",
            "accepted_subagent_stop_receipt_sha256",
            "reported_envelope_sha256",
        ):
            self.assertRegex(chain[field], SHA256)
        self.assertFalse(chain["raw_payload_stored"])

    def test_post_transition_barrier_allows_only_parent_evidence_input(self) -> None:
        barrier = self.result["post_transition_barrier"]
        frontier = self.input["git_frontier"]

        for field in ("root", "branch", "head", "head_tree", "write_tree", "index_sha256"):
            self.assertEqual(barrier[field], frontier[field])
        self.assertEqual(
            barrier["status_porcelain_v1"],
            [
                "?? probes/"
                "g4-zhipu-native-child-parent-adjudication-input-20260908.json"
            ],
        )
        self.assertTrue(barrier["only_parent_evidence_write_present"])
        self.assertTrue(barrier["candidate_process_absent"])

    def test_progress_does_not_overclaim_wait_identity_or_phase_completion(self) -> None:
        verdict = self.result["scope_verdict"]
        result_path = (
            "probes/g4-zhipu-native-child-parent-adjudication-result-20260908.json"
        )
        gates = {gate["id"]: gate for gate in self.status["phase1"]["gates"]}

        self.assertTrue(verdict["native_external_child_readonly_assignment_consumed"])
        self.assertTrue(verdict["native_external_child_sessionmeta_identity_bound"])
        self.assertTrue(verdict["native_external_child_tool_loop_observed"])
        self.assertTrue(verdict["native_external_child_parent_callback_observed"])
        self.assertFalse(verdict["wait_receiver_identity_exact"])
        self.assertFalse(verdict["identity_cohort_complete"])
        self.assertFalse(verdict["mutation_negative_space_complete"])
        self.assertFalse(verdict["strong_global_quiescence_complete"])
        self.assertFalse(verdict["phase1_complete"])
        self.assertFalse(verdict["direct_write_qualified"])
        self.assertIn(result_path, gates["P1"]["evidence"])
        self.assertEqual(gates["P1"]["state"], "qualified")
        for gate_id in ("P2", "P3", "P4", "P5b", "P6", "P6a", "P6b", "P7"):
            self.assertIn(result_path, gates[gate_id]["evidence"])
        for gate_id in ("P2", "P3", "P5b", "P6", "P6a", "P6b"):
            self.assertEqual(gates[gate_id]["state"], "qualified")
        for gate_id in ("P4", "P7"):
            self.assertEqual(gates[gate_id]["state"], "partial")
        self.assertFalse(self.status["phase1"]["declared_complete"])
        self.assertFalse(self.status["phase1"]["declared_direct_write_qualified"])
        self.assertEqual(self.status["phase2"]["state"], "closed")
        self.assertEqual(self.status["phase3"]["state"], "closed")


if __name__ == "__main__":
    unittest.main()
