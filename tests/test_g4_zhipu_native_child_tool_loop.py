import json
import pathlib
import re
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
RECEIPT_PATH = ROOT / "probes" / "g4-zhipu-native-child-tool-loop-20260907.json"
SOURCE_RECEIPT_PATH = (
    ROOT
    / "probes"
    / "current-signed-runtime-plaintext-child-provider-seam-source-candidate.json"
)
RUNTIME_INDEX_PATH = ROOT / "probes" / "codex-runtime-evidence-index.json"
STATUS_PATH = ROOT / "probes" / "phase1-g4-status.json"
SHA256 = re.compile(r"^[0-9a-f]{64}$")


class G4ZhipuNativeChildToolLoopTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.receipt = json.loads(RECEIPT_PATH.read_text())
        cls.source_receipt = json.loads(SOURCE_RECEIPT_PATH.read_text())
        cls.runtime_index = json.loads(RUNTIME_INDEX_PATH.read_text())
        cls.status = json.loads(STATUS_PATH.read_text())

    def test_runtime_is_bound_semantically_without_a_test_version_literal(self) -> None:
        role = self.runtime_index["current_runtime_role"]
        runtime = self.runtime_index["runtime_roles"][role]
        self.assertEqual(self.receipt["runtime"]["semantic_role"], role)
        self.assertEqual(self.receipt["runtime"]["codex_version"], runtime["codex_version"])
        self.assertEqual(self.receipt["runtime"]["source_commit"], runtime["source_commit"])

    def test_direct_responses_control_observed_a_real_function_call(self) -> None:
        control = self.receipt["direct_responses_function_control"]
        self.assertEqual(control["http_status"], 200)
        self.assertEqual(control["model"], "glm-5.3")
        self.assertEqual(control["output_types"], ["reasoning", "function_call"])
        self.assertEqual(control["function_call"]["name"], "probe_marker")
        self.assertTrue(control["function_call"]["call_id_present"])
        self.assertFalse(control["raw_response_retained"])
        self.assertRegex(control["request_sha256"], SHA256)
        self.assertRegex(control["response_sha256"], SHA256)

    def test_parent_and_child_provider_identity_are_distinct_and_exact(self) -> None:
        live = self.receipt["live_probe"]
        self.assertEqual(live["root"]["model_provider"], "openai")
        self.assertIsNone(live["root"]["agent_path"])
        self.assertEqual(live["child"]["model_provider"], "zhipu")
        self.assertEqual(live["child"]["model"], "glm-5.3")
        self.assertEqual(
            live["child"]["canonical_agent_path"],
            "/root/g4_zhipu_native_tools_2",
        )
        self.assertEqual(
            live["child"]["runtime_session_id"], live["root"]["thread_id"]
        )
        self.assertEqual(live["child"]["sandbox_policy"], "read-only")

    def test_native_tool_call_and_hook_receipts_join_on_tool_use_id(self) -> None:
        live = self.receipt["live_probe"]
        tool = live["tool_loop"]
        self.assertEqual(tool["name"], "list_agents")
        self.assertEqual(tool["arguments"], {})
        self.assertEqual(tool["exit_code"], 0)
        self.assertRegex(tool["output_sha256"], SHA256)
        pretool = next(
            event
            for event in live["hook_chain"]
            if event.get("tool_use_id") == tool["call_id"]
        )
        self.assertEqual(pretool["event"], "PreToolUse")
        self.assertEqual(pretool["scope"], "target_child")
        self.assertEqual(pretool["tool_name"], "g4_assignmentlist_agents")
        self.assertEqual(
            [event["event"] for event in live["hook_chain"]].count("SubagentStart"),
            1,
        )
        self.assertEqual(
            [event["event"] for event in live["hook_chain"]].count("SubagentStop"),
            3,
        )

    def test_final_attestation_and_parent_callback_remain_read_only(self) -> None:
        live = self.receipt["live_probe"]
        final = live["final_attestation"]
        baseline = live["git_baseline"]
        self.assertEqual(final["verification_exit_code"], 0)
        self.assertTrue(final["callback_received_by_openai_parent"])
        self.assertFalse(final["context_lost"])
        self.assertFalse(final["authority_violation"])
        self.assertTrue(final["assigned_slice_complete"])
        self.assertFalse(baseline["index_changed"])
        self.assertEqual(baseline["git_status_short"], "")
        self.assertEqual(baseline["changed_paths"], [])
        self.assertTrue(live["post_callback_observation"]["candidate_process_absent"])
        self.assertFalse(
            live["post_callback_observation"]["strong_global_quiescence_qualified"]
        )

    def test_credential_boundary_and_phase_gates_remain_closed(self) -> None:
        credential = self.receipt["credential_boundary"]
        self.assertTrue(credential["credential_present"])
        for key in (
            "value_in_argv",
            "value_printed",
            "value_hashed",
            "value_retained",
            "value_committed",
        ):
            self.assertFalse(credential[key])
        verdict = self.receipt["verdict"]
        self.assertTrue(verdict["native_external_child_readonly_tool_loop_qualified"])
        self.assertFalse(verdict["native_external_child_broadly_qualified"])
        self.assertFalse(verdict["mutation_qualified"])
        self.assertFalse(verdict["phase1_complete"])
        self.assertFalse(verdict["direct_write_qualified"])
        self.assertEqual(verdict["phase2_state"], "closed")
        self.assertEqual(verdict["phase3_state"], "closed")

    def test_source_receipt_points_to_the_live_receipt(self) -> None:
        self.assertEqual(
            self.source_receipt["live_boundaries"]["live_receipt"],
            "probes/g4-zhipu-native-child-tool-loop-20260907.json",
        )
        self.assertTrue(
            self.source_receipt["verdict"][
                "native_external_child_readonly_tool_loop_qualified"
            ]
        )
        self.assertFalse(self.source_receipt["verdict"]["native_external_child_qualified"])

    def test_phase_matrix_records_partial_evidence_without_opening_later_phases(self) -> None:
        receipt_path = "probes/g4-zhipu-native-child-tool-loop-20260907.json"
        gates = {gate["id"]: gate for gate in self.status["phase1"]["gates"]}
        for gate_id in ("P1", "P2", "P3", "P4", "P5b", "P6", "P6a", "P6b", "P7"):
            self.assertIn(receipt_path, gates[gate_id]["evidence"])
            self.assertNotEqual(gates[gate_id]["state"], "complete")
        self.assertTrue(self.status["phase1"]["declared_complete"])
        self.assertTrue(self.status["phase1"]["declared_direct_write_qualified"])
        self.assertEqual(self.status["phase2"]["state"], "closed")
        self.assertEqual(self.status["phase3"]["state"], "closed")
        self.assertFalse(self.status["phase3"]["implementation_opened"])


if __name__ == "__main__":
    unittest.main()
