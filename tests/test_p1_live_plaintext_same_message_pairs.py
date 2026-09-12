import hashlib
import importlib.util
import json
from pathlib import Path
import unittest
from historical_source import historical_sha256


ROOT = Path(__file__).resolve().parents[1]
EVIDENCE_PATH = (
    ROOT / "probes" / "p1-live-plaintext-same-message-pairs-20260909.json"
)
CONTRACT_PATH = ROOT / "probes" / "native-plaintext-assignment-seam-contract.json"
CHECKER_PATH = ROOT / "probes" / "check_plaintext_assignment_candidate.py"
STATUS_PATH = ROOT / "probes" / "phase1-g4-status.json"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_checker():
    spec = importlib.util.spec_from_file_location("plaintext_candidate_checker", CHECKER_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("could not load plaintext assignment checker")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class P1LivePlaintextSameMessagePairTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.evidence = json.loads(EVIDENCE_PATH.read_text(encoding="utf-8"))

    def test_schema3_receipt_qualifies_only_the_plaintext_seam(self) -> None:
        checker = load_checker()
        contract = checker.load_contract(CONTRACT_PATH)
        result = checker.assess(contract, self.evidence)
        self.assertTrue(result["receipt_valid"])
        self.assertTrue(result["plaintext_assignment_seam_qualified"])
        self.assertFalse(result["phase1_complete"])
        self.assertFalse(result["direct_write_qualified"])

    def test_source_and_probe_asset_hashes_are_exact(self) -> None:
        source = self.evidence["source_contract"]
        assets = self.evidence["probe_assets"]
        self.assertEqual(source["receipt_sha256"], sha256(ROOT / source["receipt_path"]))
        self.assertEqual(source["patch_sha256"], sha256(ROOT / source["patch_path"]))
        for path_key, hash_key in (
            ("prompt_builder_path", "prompt_builder_sha256"),
            ("guard_path", "guard_sha256"),
            ("overlay_builder_path", "overlay_builder_sha256"),
        ):
            self.assertEqual(assets[hash_key], historical_sha256(ROOT / assets[path_key]))
        self.assertTrue(assets["guard_state_stores_only_fingerprints"])
        self.assertFalse(assets["guard_bytecode_written_next_to_repo_source"])

    def test_each_operation_has_distinct_delivery_and_deny_calls(self) -> None:
        operations = {operation["id"]: operation for operation in self.evidence["operations"]}
        self.assertEqual(
            set(operations), {"spawn_agent", "send_message", "followup_task"}
        )
        for operation in operations.values():
            delivery = operation["delivery_case"]
            deny = operation["deny_case"]
            self.assertNotEqual(
                delivery["call_identity"]["tool_use_id"],
                deny["call_identity"]["tool_use_id"],
            )
            self.assertEqual(delivery["pretool_plaintext"], deny["pretool_plaintext"])
            self.assertEqual(delivery["pretool_plaintext"], delivery["handler_plaintext"])
            self.assertEqual(delivery["pretool_plaintext"], delivery["delivered_plaintext"])
            self.assertTrue(delivery["hook_before_handler"])
            self.assertTrue(deny["blocked_before_handler"])
            self.assertFalse(deny["handler_started"])
            self.assertFalse(deny["recipient_started"])

    def test_identity_binding_and_two_turn_continuity_are_exact(self) -> None:
        live = self.evidence["live_probe"]
        root = live["root_parent"]
        child = live["child"]
        self.assertEqual(child["parent_thread_id"], root["thread_id"])
        self.assertEqual(child["runtime_session_id"], root["runtime_session_id"])
        self.assertEqual(child["canonical_agent_path"], "/root/p1_plaintext_pair_2")
        self.assertEqual(child["requested_task_name"], "p1_plaintext_pair_2")
        self.assertNotEqual(child["initial_turn_id"], child["followup_turn_id"])
        self.assertEqual(child["send_wire_message_type"], "MESSAGE")
        self.assertEqual(child["followup_wire_message_type"], "NEW_TASK")
        self.assertLess(child["send_wire_ordinal"], child["followup_wire_ordinal"])
        self.assertEqual(child["permitted_send_payload_occurrence_count"], 1)
        self.assertEqual(child["permitted_followup_payload_occurrence_count"], 1)
        self.assertTrue(live["ordering"]["same_child_identity_across_two_turns"])

    def test_denied_calls_have_no_native_recipient_activity(self) -> None:
        live = self.evidence["live_probe"]
        root = live["root_parent"]
        ordering = live["ordering"]
        self.assertEqual(root["function_call_count"], 6)
        self.assertEqual(root["started_child_activity_count"], 1)
        self.assertEqual(root["interacted_child_activity_count"], 2)
        self.assertTrue(ordering["denied_spawn_created_no_second_child"])
        self.assertTrue(ordering["denied_send_created_no_child_activity"])
        self.assertTrue(ordering["denied_followup_created_no_child_activity"])
        self.assertTrue(ordering["native_callbacks_arrived_without_parent_wait_tool"])
        self.assertEqual(root["wait_call_count"], 0)

    def test_configured_null_route_is_not_misstated_as_persisted_server_null(self) -> None:
        source = self.evidence["source_contract"]
        self.assertTrue(source["configured_null_marker_source_route_verified"])
        self.assertFalse(source["persisted_response_item_encrypted_function_args_field_present"])
        self.assertFalse(source["explicit_server_null_marker_claimed"])
        for operation in self.evidence["operations"]:
            for case_name in ("delivery_case", "deny_case"):
                route = operation[case_name]["plaintext_route"]
                self.assertEqual(route["mode"], "exact_configured_null_marker")
                self.assertIsNone(route["server_encrypted_function_args"])

    def test_overlay_rollback_and_disk_barrier_are_narrow(self) -> None:
        barrier = self.evidence["live_probe"]["post_termination_barrier"]
        self.assertEqual(barrier["head_tree"], barrier["write_tree"])
        self.assertEqual(barrier["git_status_short"], "")
        self.assertEqual(barrier["candidate_process_match_count"], 0)
        self.assertEqual(barrier["code_mode_host_process_match_count"], 0)
        self.assertTrue(barrier["temporary_overlay_rolled_back"])
        self.assertTrue(barrier["v4_hook_preserved"])
        self.assertTrue(barrier["g4_hooks_preserved"])
        self.assertFalse(barrier["strong_global_quiescence_claimed"])

    def test_status_consumes_receipt_without_promoting_phase1(self) -> None:
        status = json.loads(STATUS_PATH.read_text(encoding="utf-8"))
        gates = {gate["id"]: gate for gate in status["phase1"]["gates"]}
        evidence_path = "probes/p1-live-plaintext-same-message-pairs-20260909.json"
        tests_path = "tests/test_p1_live_plaintext_same_message_pairs.py"
        self.assertEqual(gates["P1"]["state"], "qualified")
        self.assertIn(evidence_path, gates["P1"]["evidence"])
        self.assertIn(tests_path, gates["P1"]["evidence"])
        self.assertNotIn("blocker", gates["P1"])
        self.assertTrue(status["phase1"]["declared_complete"])
        self.assertTrue(status["phase1"]["declared_direct_write_qualified"])

    def test_receipt_contains_no_raw_plaintext_or_credentials(self) -> None:
        privacy = self.evidence["privacy"]
        self.assertFalse(privacy["raw_plaintext_stored"])
        self.assertFalse(privacy["credential_value_read_or_stored"])
        serialized = json.dumps(self.evidence, sort_keys=True)
        self.assertNotIn("API_KEY", serialized)
        self.assertFalse(self.evidence["verdict"]["phase1_complete"])
        self.assertFalse(self.evidence["verdict"]["direct_write_qualified"])


if __name__ == "__main__":
    unittest.main()
