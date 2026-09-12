import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "probes" / "check_plaintext_assignment_candidate.py"
CONTRACT = ROOT / "probes" / "native-plaintext-assignment-seam-contract.json"

SPEC = importlib.util.spec_from_file_location(
    "check_plaintext_assignment_candidate", SCRIPT
)
check_candidate = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(check_candidate)


def fingerprint(value):
    return {"length": len(value), "sha256": "a" * 64}


def valid_receipt(contract):
    operations = []
    for index, operation_id in enumerate(contract["required_operations"], start=1):
        value = f"exact-{operation_id}"
        delivery_identity = {
            "parent_session_id": "01a00147-39cb-7b50-b78d-7baed910eb45",
            "parent_agent_path": "/root",
            "parent_turn_id": f"00000000-0000-0000-0000-{index:012d}",
            "tool_use_id": f"delivery-{operation_id}",
            "target_session_id": f"10000000-0000-0000-0000-{index:012d}",
            "canonical_agent_path": f"/root/{operation_id}",
        }
        deny_identity = {
            "parent_session_id": "01a00147-39cb-7b50-b78d-7baed910eb45",
            "parent_agent_path": "/root",
            "parent_turn_id": f"20000000-0000-0000-0000-{index:012d}",
            "tool_use_id": f"deny-{operation_id}",
        }
        if operation_id == "spawn_agent":
            delivery_identity["requested_task_name"] = "g4_plaintext_pair"
            deny_identity["requested_task_name"] = "g4_plaintext_pair"
        operations.append(
            {
                "id": operation_id,
                "hook_tool_name": contract["required_hook_tool_names"][operation_id],
                "delivery_case": {
                    "call_identity": delivery_identity,
                    "schema_message_encrypted": False,
                    "plaintext_route": {
                        "mode": "exact_configured_null_marker",
                        "server_encrypted_function_args": None,
                        "configured_tool_namespace": contract["required_tool_namespace"],
                        "configured_operation": operation_id,
                        "exact_session_opt_in": True,
                    },
                    "pretool_plaintext": fingerprint(value),
                    "handler_plaintext": fingerprint(value),
                    "delivered_plaintext": fingerprint(value),
                    "encrypted_content_present": False,
                    "hook_before_handler": True,
                    "native_multi_agent_v2": True,
                },
                "deny_case": {
                    "call_identity": deny_identity,
                    "schema_message_encrypted": False,
                    "plaintext_route": {
                        "mode": "exact_configured_null_marker",
                        "server_encrypted_function_args": None,
                        "configured_tool_namespace": contract["required_tool_namespace"],
                        "configured_operation": operation_id,
                        "exact_session_opt_in": True,
                    },
                    "pretool_plaintext": fingerprint(value),
                    "native_multi_agent_v2": True,
                    "blocked_before_handler": True,
                    "handler_started": False,
                    "recipient_started": False,
                },
            }
        )
    return {
        "schema": contract["schema"],
        "contract_schema": contract["schema"],
        "evidence_kind": "live_native",
        "codex_version": "candidate",
        "source_commit": "b" * 40,
        "runtime": {
            "candidate_binary_sha256": "c" * 64,
            "candidate_patch_sha256": "d" * 64,
            "selected_executable": "/tmp/codex-candidate",
            "selection_mechanism": "direct_executable",
            "signed_app_resource_replaced": False,
            "headless_only": True,
            "gui_app_server_selected": False,
        },
        "configuration": {
            "default_message_delivery": "encrypted",
            "active_message_delivery": "plaintext",
            "explicit_opt_in": True,
            "parent_provider": "openai",
            "parent_auth_unchanged": True,
            "parent_base_url_unchanged": True,
            "live_config_modified": False,
            "native_multi_agent_v2": True,
            "tool_namespace": contract["required_tool_namespace"],
            "configured_plaintext_operations": sorted(
                contract["required_operations"]
            ),
            "null_marker_plaintext_requires_exact_route": True,
            "unconfigured_null_marker_remains_encrypted": True,
        },
        "operations": operations,
        "regressions": {
            "encrypted_mode_still_encrypted": True,
            "unconfigured_null_marker_still_encrypted": True,
            "nonempty_private_marker_fails_closed": True,
            "v1_fallback_used": False,
            "native_agent_control_preserved": True,
        },
        "privacy": {
            "raw_plaintext_stored": False,
            "credential_value_read_or_stored": False,
        },
    }


class PlaintextAssignmentCandidateTests(unittest.TestCase):
    def test_missing_live_receipt_fails_closed(self):
        contract = check_candidate.load_contract(CONTRACT)
        result = check_candidate.assess(contract, None)

        self.assertFalse(result["receipt_valid"])
        self.assertFalse(result["plaintext_assignment_seam_qualified"])
        self.assertFalse(result["phase1_complete"])
        self.assertFalse(result["direct_write_qualified"])

    def test_complete_receipt_qualifies_only_the_assignment_seam(self):
        contract = check_candidate.load_contract(CONTRACT)
        result = check_candidate.assess(contract, valid_receipt(contract))

        self.assertTrue(result["receipt_valid"])
        self.assertTrue(result["plaintext_assignment_seam_qualified"])
        self.assertFalse(result["phase1_complete"])
        self.assertFalse(result["direct_write_qualified"])

    def test_end_to_end_plaintext_mismatch_is_rejected(self):
        contract = check_candidate.load_contract(CONTRACT)
        receipt = valid_receipt(contract)
        receipt["operations"][0]["delivery_case"]["delivered_plaintext"][
            "sha256"
        ] = "c" * 64

        with self.assertRaisesRegex(ValueError, "not end-to-end identical"):
            check_candidate.assess(contract, receipt)

    def test_explicit_empty_marker_route_remains_valid(self):
        contract = check_candidate.load_contract(CONTRACT)
        receipt = valid_receipt(contract)
        for operation in receipt["operations"]:
            for case_name in ("delivery_case", "deny_case"):
                route = operation[case_name]["plaintext_route"]
                route["mode"] = "explicit_empty_marker"
                route["server_encrypted_function_args"] = []

        result = check_candidate.assess(contract, receipt)

        self.assertTrue(result["plaintext_assignment_seam_qualified"])

    def test_null_marker_without_exact_route_fails_closed(self):
        contract = check_candidate.load_contract(CONTRACT)
        receipt = valid_receipt(contract)
        receipt["operations"][0]["delivery_case"]["plaintext_route"][
            "exact_session_opt_in"
        ] = False

        with self.assertRaisesRegex(ValueError, "lacks exact session opt-in"):
            check_candidate.assess(contract, receipt)

    def test_null_marker_wrong_namespace_fails_closed(self):
        contract = check_candidate.load_contract(CONTRACT)
        receipt = valid_receipt(contract)
        receipt["operations"][0]["delivery_case"]["plaintext_route"][
            "configured_tool_namespace"
        ] = "g4_assignment_extra"

        with self.assertRaisesRegex(ValueError, "namespace is not exact"):
            check_candidate.assess(contract, receipt)

    def test_null_marker_wrong_operation_fails_closed(self):
        contract = check_candidate.load_contract(CONTRACT)
        receipt = valid_receipt(contract)
        receipt["operations"][0]["delivery_case"]["plaintext_route"][
            "configured_operation"
        ] = "send_message"

        with self.assertRaisesRegex(ValueError, "operation is not exact"):
            check_candidate.assess(contract, receipt)

    def test_route_mode_and_marker_must_agree(self):
        contract = check_candidate.load_contract(CONTRACT)
        receipt = valid_receipt(contract)
        receipt["operations"][0]["delivery_case"]["plaintext_route"][
            "server_encrypted_function_args"
        ] = []

        with self.assertRaisesRegex(ValueError, "configured-null route marker is invalid"):
            check_candidate.assess(contract, receipt)

    def test_delivery_and_deny_must_be_distinct_calls(self):
        contract = check_candidate.load_contract(CONTRACT)
        receipt = valid_receipt(contract)
        operation = receipt["operations"][0]
        operation["deny_case"]["call_identity"]["tool_use_id"] = operation[
            "delivery_case"
        ]["call_identity"]["tool_use_id"]

        with self.assertRaisesRegex(ValueError, "must be distinct calls"):
            check_candidate.assess(contract, receipt)

    def test_delivery_and_deny_must_use_exact_message_bytes(self):
        contract = check_candidate.load_contract(CONTRACT)
        receipt = valid_receipt(contract)
        receipt["operations"][0]["deny_case"]["pretool_plaintext"]["sha256"] = (
            "e" * 64
        )

        with self.assertRaisesRegex(ValueError, "exact message bytes"):
            check_candidate.assess(contract, receipt)

    def test_root_target_and_windows_candidate_path_remain_valid(self):
        contract = check_candidate.load_contract(CONTRACT)
        receipt = valid_receipt(contract)
        receipt["runtime"]["selected_executable"] = r"C:\\Codex\\codex.exe"
        receipt["operations"][1]["delivery_case"]["call_identity"][
            "canonical_agent_path"
        ] = "/root"

        result = check_candidate.assess(contract, receipt)
        self.assertTrue(result["plaintext_assignment_seam_qualified"])

    def test_gui_app_server_selection_is_rejected(self):
        contract = check_candidate.load_contract(CONTRACT)
        receipt = valid_receipt(contract)
        receipt["runtime"]["selection_mechanism"] = "CODEX_CLI_PATH"
        receipt["runtime"]["gui_app_server_selected"] = True

        with self.assertRaisesRegex(ValueError, "selection mechanism is invalid"):
            check_candidate.assess(contract, receipt)

    def test_historical_schema_two_receipt_cannot_satisfy_schema_three(self):
        contract = check_candidate.load_contract(CONTRACT)
        receipt = valid_receipt(contract)
        receipt["schema"] = 2
        receipt["contract_schema"] = 2

        with self.assertRaisesRegex(ValueError, "schema 3"):
            check_candidate.assess(contract, receipt)

    def test_agent_path_prefix_collision_is_rejected(self):
        contract = check_candidate.load_contract(CONTRACT)
        receipt = valid_receipt(contract)
        receipt["operations"][0]["delivery_case"]["call_identity"][
            "parent_agent_path"
        ] = "/rooted"

        with self.assertRaisesRegex(ValueError, "parent AgentPath is invalid"):
            check_candidate.assess(contract, receipt)

    def test_transport_opt_in_cannot_grant_mutation_authority(self):
        contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
        contract["boundaries"]["opt_in_grants_mutation_authority"] = True
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "contract.json"
            path.write_text(json.dumps(contract), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "forbidden boundary"):
                check_candidate.load_contract(path)

    def test_require_qualified_without_receipt_exits_two(self):
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "--require-qualified"],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )

        self.assertEqual(result.returncode, 2, result.stderr)
        output = json.loads(result.stdout)
        self.assertTrue(output["valid"])
        self.assertFalse(output["plaintext_assignment_seam_qualified"])


if __name__ == "__main__":
    unittest.main()
