import hashlib
import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
EVIDENCE_PATH = ROOT / "probes" / "p1-live-plaintext-message-delivery-20260908.json"
STATUS_PATH = ROOT / "probes" / "phase1-g4-status.json"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


class P1LivePlaintextMessageDeliveryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.evidence = json.loads(EVIDENCE_PATH.read_text(encoding="utf-8"))

    def test_source_contract_and_probe_builder_hashes_are_exact(self) -> None:
        source = self.evidence["source_contract"]
        prompt = self.evidence["probe_prompt"]
        self.assertEqual(source["receipt_sha256"], sha256(ROOT / source["receipt_path"]))
        self.assertEqual(source["patch_sha256"], sha256(ROOT / source["patch_path"]))
        self.assertEqual(prompt["builder_sha256"], sha256(ROOT / prompt["builder_path"]))
        self.assertEqual(
            source["configured_plaintext_tools"],
            ["spawn_agent", "send_message", "followup_task"],
        )
        self.assertEqual(source["plaintext_model_input_type"], "message")
        self.assertEqual(source["plaintext_model_input_role"], "user")
        self.assertTrue(source["encrypted_default_preserved"])

    def test_payload_preimages_are_absent_from_initial_child_assignment(self) -> None:
        prompt = self.evidence["probe_prompt"]
        self.assertFalse(prompt["initial_child_assignment_contains_send_payload"])
        self.assertFalse(prompt["initial_child_assignment_contains_followup_payload"])
        child = self.evidence["live_probe"]["child"]
        head = self.evidence["repository"]["source_commit"]
        send_payload = f"P1-PLAINTEXT-SEND-V1-{head}"
        followup_payload = f"P1-PLAINTEXT-FOLLOWUP-V1-{head}"
        self.assertEqual(child["send_payload"]["sha256"], sha256_text(send_payload))
        self.assertEqual(child["send_payload"]["bytes"], len(send_payload))
        self.assertEqual(child["send_payload"]["rollout_occurrence_count"], 1)
        self.assertEqual(
            child["followup_payload"]["sha256"], sha256_text(followup_payload)
        )
        self.assertEqual(child["followup_payload"]["bytes"], len(followup_payload))
        self.assertEqual(child["followup_payload"]["rollout_occurrence_count"], 1)

    def test_sessionmeta_identity_persists_across_idle_followup_turn(self) -> None:
        live = self.evidence["live_probe"]
        root = live["root_parent"]
        child = live["child"]
        self.assertEqual(child["parent_thread_id"], root["thread_id"])
        self.assertEqual(child["runtime_session_id"], root["runtime_session_id"])
        self.assertEqual(child["depth"], 1)
        self.assertEqual(
            child["canonical_agent_path"],
            f"/root/{child['requested_task_name']}",
        )
        self.assertTrue(child["sessionmeta_identity_exact"])
        self.assertNotEqual(
            child["initial_turn"]["turn_id"],
            child["followup_turn"]["turn_id"],
        )
        self.assertTrue(live["ordering"]["same_child_thread_and_canonical_path_across_turns"])

    def test_send_and_followup_arrive_as_two_plaintext_user_messages(self) -> None:
        child = self.evidence["live_probe"]["child"]
        initial = child["initial_turn"]
        followup = child["followup_turn"]
        self.assertEqual(initial["assignment_wire_type"], "message")
        self.assertEqual(initial["assignment_wire_role"], "user")
        self.assertTrue(initial["assignment_trigger_turn"])
        self.assertEqual(followup["send_wire_type"], "message")
        self.assertEqual(followup["send_wire_role"], "user")
        self.assertEqual(followup["send_wire_message_type"], "MESSAGE")
        self.assertFalse(followup["send_trigger_turn"])
        self.assertEqual(followup["followup_wire_type"], "message")
        self.assertEqual(followup["followup_wire_role"], "user")
        self.assertEqual(followup["followup_wire_message_type"], "NEW_TASK")
        self.assertTrue(followup["followup_trigger_turn"])
        self.assertLess(followup["send_wire_ordinal"], followup["followup_wire_ordinal"])
        self.assertEqual(child["incoming_inter_agent_user_message_count"], 3)
        self.assertEqual(child["incoming_agent_message_response_item_count"], 0)
        self.assertEqual(child["mutation_tool_call_count"], 0)

    def test_queue_only_and_trigger_turn_order_is_exact(self) -> None:
        root = self.evidence["live_probe"]["root_parent"]
        ordering = self.evidence["live_probe"]["ordering"]
        self.assertEqual(root["send_message_result"], "")
        self.assertEqual(root["followup_task_result"], "")
        self.assertEqual(root["wait_call_count"], 2)
        self.assertEqual(root["wait_timeout_count"], 0)
        for field in (
            "initial_turn_completed_before_send_message",
            "send_message_accepted_before_followup_task",
            "queue_only_send_did_not_start_a_turn",
            "followup_task_started_second_turn",
            "send_wire_precedes_followup_wire",
            "both_wires_precede_second_turn_final",
        ):
            self.assertTrue(ordering[field])

    def test_transport_sample_does_not_claim_g4_or_mutation_authority(self) -> None:
        state = self.evidence["live_probe"]["g4_state_boundary"]
        self.assertFalse(state["target_role"])
        self.assertFalse(state["g4_authority_state_expected"])
        self.assertFalse(state["g4_authority_state_created"])
        barrier = self.evidence["live_probe"]["post_termination_barrier"]
        self.assertEqual(barrier["head_tree"], barrier["write_tree"])
        self.assertEqual(barrier["git_status_short"], "")
        self.assertEqual(barrier["candidate_process_match_count"], 0)
        self.assertEqual(barrier["code_mode_host_process_match_count"], 0)
        self.assertFalse(barrier["strong_global_quiescence_claimed"])
        scope = self.evidence["scope_boundary"]
        self.assertFalse(scope["worker_narrative_used_as_transport_authority"])
        self.assertFalse(scope["g4_capsule_or_mutation_authority_claimed"])
        self.assertFalse(scope["mixed_provider_delivery_observed"])
        self.assertFalse(scope["broader_delivery_cohort_complete"])
        verification = self.evidence["verification"]
        self.assertEqual(verification["focused_suite"]["test_count"], 18)
        self.assertEqual(verification["provider_free_suite"]["test_count"], 616)
        self.assertEqual(verification["provider_free_suite"]["exit_code"], 0)
        self.assertEqual(
            verification["provider_free_suite"]["agent_template_checks"],
            "passed",
        )
        self.assertEqual(verification["phase1_gate"]["require_complete_exit_code"], 2)
        self.assertEqual(verification["mutation_matrix"]["blocker_count"], 13)
        self.assertFalse(verification["same_uid_trust"]["same_uid_rollout_protected"])
        self.assertFalse(verification["same_uid_trust"]["same_uid_state_protected"])
        self.assertEqual(
            verification["hook_event_chain"]["pending_tool_use_ids"],
            ["exec-04d901ca-1eb5-4ecf-a046-16440788c4d3"],
        )

    def test_status_closes_only_live_message_subgaps(self) -> None:
        status = json.loads(STATUS_PATH.read_text(encoding="utf-8"))
        gates = {gate["id"]: gate for gate in status["phase1"]["gates"]}
        evidence_path = "probes/p1-live-plaintext-message-delivery-20260908.json"
        self.assertEqual(gates["P1"]["state"], "qualified")
        self.assertIn(evidence_path, gates["P1"]["evidence"])
        self.assertNotIn("blocker", gates["P1"])
        for gate_id in ("P2", "P3", "P7"):
            self.assertEqual(gates[gate_id]["state"], "partial")
            self.assertIn(evidence_path, gates[gate_id]["evidence"])
        self.assertFalse(status["phase1"]["declared_complete"])
        self.assertFalse(status["phase1"]["declared_direct_write_qualified"])

    def test_no_credential_value_or_name_is_stored(self) -> None:
        self.assertFalse(self.evidence["runtime"]["credential_values_observed_or_recorded"])
        self.assertFalse(self.evidence["verdict"]["phase1_complete"])
        self.assertFalse(self.evidence["verdict"]["direct_write_qualified"])
        self.assertNotIn("API_KEY", json.dumps(self.evidence, sort_keys=True))


if __name__ == "__main__":
    unittest.main()
