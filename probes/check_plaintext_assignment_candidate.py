#!/usr/bin/env python3

import argparse
import json
from pathlib import Path
import re
import sys


REQUIRED_OPERATIONS = {"spawn_agent", "send_message", "followup_task"}
REQUIRED_INVARIANTS = {
    "explicit_opt_in_default_encrypted",
    "plaintext_schema_signal",
    "exact_configured_null_marker_route",
    "unconfigured_null_marker_regression",
    "headless_candidate_selection",
    "exact_pretool_plaintext",
    "separate_delivery_and_deny_calls",
    "deny_before_dispatch",
    "exact_delivered_bytes",
    "native_multi_agent_v2_preserved",
    "private_branch_fails_closed",
    "encrypted_mode_regression",
    "openai_parent_unchanged",
    "evidence_redacted",
}
REQUIRED_CASES = {"delivery_case", "deny_case"}
REQUIRED_RUNTIME_FIELDS = {
    "candidate_binary_sha256",
    "candidate_patch_sha256",
    "selected_executable",
    "selection_mechanism",
    "signed_app_resource_replaced",
    "headless_only",
    "gui_app_server_selected",
}
REQUIRED_CALL_IDENTITY_FIELDS = {
    "parent_session_id",
    "parent_agent_path",
    "parent_turn_id",
    "tool_use_id",
}
SHA256 = re.compile(r"^[0-9a-f]{64}$")
GIT_OID = re.compile(r"^[0-9a-f]{40}$|^[0-9a-f]{64}$")
SESSION_ID = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
)
TASK_NAME = re.compile(r"^[a-z0-9_]+$")
AGENT_PATH = re.compile(r"^/root(?:/[a-z0-9_]+)*$")
ABSOLUTE_EXECUTABLE = re.compile(r"^(?:/|[A-Za-z]:[\\/])")
PLAINTEXT_ROUTE_FIELDS = {
    "mode",
    "server_encrypted_function_args",
    "configured_tool_namespace",
    "configured_operation",
    "exact_session_opt_in",
}


def load_contract(path):
    value = json.loads(path.read_text(encoding="utf-8"))
    if value.get("schema") != 3:
        raise ValueError("plaintext assignment contract has an invalid schema")
    if set(value.get("required_operations", [])) != REQUIRED_OPERATIONS:
        raise ValueError("plaintext assignment contract has incomplete operations")
    if set(value.get("required_invariants", [])) != REQUIRED_INVARIANTS:
        raise ValueError("plaintext assignment contract has incomplete invariants")
    if set(value.get("required_cases_per_operation", [])) != REQUIRED_CASES:
        raise ValueError("plaintext assignment contract has incomplete paired cases")
    case_semantics = value.get("case_semantics")
    if (
        not isinstance(case_semantics, dict)
        or case_semantics.get("same_message_bytes_across_cases") is not True
        or case_semantics.get("one_call_may_satisfy_both_cases") is not False
        or case_semantics.get(
            "null_marker_requires_exact_namespace_operation_and_session_opt_in"
        )
        is not True
    ):
        raise ValueError("plaintext assignment contract conflates delivery and deny cases")
    if set(value.get("required_runtime_fields", [])) != REQUIRED_RUNTIME_FIELDS:
        raise ValueError("plaintext assignment contract has incomplete runtime provenance")
    if set(value.get("required_call_identity_fields", [])) != REQUIRED_CALL_IDENTITY_FIELDS:
        raise ValueError("plaintext assignment contract has incomplete call identity")
    if value.get("default_mode") != "encrypted":
        raise ValueError("plaintext assignment transport must remain opt-in")
    if value.get("qualification_mode") != "plaintext":
        raise ValueError("plaintext assignment qualification mode is invalid")
    if value.get("required_tool_namespace") != "g4_assignment":
        raise ValueError("plaintext assignment contract has an invalid tool namespace")
    if set(value.get("allowed_live_plaintext_route_modes", [])) != {
        "explicit_empty_marker",
        "exact_configured_null_marker",
    }:
        raise ValueError("plaintext assignment contract has invalid route modes")

    boundaries = value.get("boundaries")
    if not isinstance(boundaries, dict):
        raise ValueError("plaintext assignment contract is missing boundaries")
    required_false = {
        "opt_in_grants_mutation_authority",
        "v1_fallback_allowed",
        "parent_provider_change_allowed",
        "credential_in_assignment_allowed",
        "raw_plaintext_in_receipt_allowed",
        "worker_narrative_is_integration_authority",
        "null_marker_plaintext_without_exact_route_allowed",
        "gui_app_server_selection_allowed",
    }
    if any(boundaries.get(key) is not False for key in required_false):
        raise ValueError("plaintext assignment contract expands a forbidden boundary")
    if boundaries.get("opt_in_is_assignment_transport_only") is not True:
        raise ValueError("plaintext opt-in must remain assignment-transport-only")

    qualification = value.get("qualification")
    if not isinstance(qualification, dict):
        raise ValueError("plaintext assignment contract is missing qualification")
    if qualification.get("requires_live_native_receipt") is not True:
        raise ValueError("plaintext assignment seam requires live native evidence")
    if qualification.get("qualifies_only_plaintext_assignment_seam") is not True:
        raise ValueError("plaintext assignment contract has an invalid scope")
    if qualification.get("completes_phase1") is not False:
        raise ValueError("plaintext assignment seam cannot complete Phase 1")
    if qualification.get("qualifies_direct_write") is not False:
        raise ValueError("plaintext assignment seam cannot qualify direct write")
    return value


def _fingerprint(value, label):
    if not isinstance(value, dict):
        raise ValueError(f"{label} fingerprint is missing")
    length = value.get("length")
    sha256 = value.get("sha256")
    if not isinstance(length, int) or length <= 0:
        raise ValueError(f"{label} fingerprint length is invalid")
    if not isinstance(sha256, str) or SHA256.fullmatch(sha256) is None:
        raise ValueError(f"{label} fingerprint sha256 is invalid")
    return {"length": length, "sha256": sha256}


def _call_identity(value, label, *, delivery):
    if not isinstance(value, dict):
        raise ValueError(f"{label} call identity is missing")
    if set(REQUIRED_CALL_IDENTITY_FIELDS) - set(value):
        raise ValueError(f"{label} call identity is incomplete")
    for key in ("parent_session_id", "parent_turn_id"):
        if not isinstance(value.get(key), str) or SESSION_ID.fullmatch(value[key]) is None:
            raise ValueError(f"{label} {key} is invalid")
    parent_path = value.get("parent_agent_path")
    if not isinstance(parent_path, str) or AGENT_PATH.fullmatch(parent_path) is None:
        raise ValueError(f"{label} parent AgentPath is invalid")
    tool_use_id = value.get("tool_use_id")
    if not isinstance(tool_use_id, str) or not tool_use_id.strip():
        raise ValueError(f"{label} tool-use identity is invalid")
    if delivery:
        target_session_id = value.get("target_session_id")
        if (
            not isinstance(target_session_id, str)
            or SESSION_ID.fullmatch(target_session_id) is None
        ):
            raise ValueError(f"{label} target session identity is invalid")
        canonical_path = value.get("canonical_agent_path")
        if (
            not isinstance(canonical_path, str)
            or AGENT_PATH.fullmatch(canonical_path) is None
        ):
            raise ValueError(f"{label} canonical AgentPath is invalid")
    return value


def _plaintext_route(value, operation_id, label, contract):
    if not isinstance(value, dict) or set(value) != PLAINTEXT_ROUTE_FIELDS:
        raise ValueError(f"{label} plaintext route fields are not exact")
    mode = value["mode"]
    if mode not in contract["allowed_live_plaintext_route_modes"]:
        raise ValueError(f"{label} plaintext route mode is invalid")
    if value["configured_tool_namespace"] != contract["required_tool_namespace"]:
        raise ValueError(f"{label} plaintext route namespace is not exact")
    if value["configured_operation"] != operation_id:
        raise ValueError(f"{label} plaintext route operation is not exact")
    if value["exact_session_opt_in"] is not True:
        raise ValueError(f"{label} plaintext route lacks exact session opt-in")
    marker = value["server_encrypted_function_args"]
    if mode == "explicit_empty_marker" and marker != []:
        raise ValueError(f"{label} explicit-empty route marker is invalid")
    if mode == "exact_configured_null_marker" and marker is not None:
        raise ValueError(f"{label} configured-null route marker is invalid")
    return value


def assess(contract, receipt):
    if receipt is None:
        return {
            "receipt_valid": False,
            "plaintext_assignment_seam_qualified": False,
            "phase1_complete": False,
            "direct_write_qualified": False,
            "blocker": "no live native plaintext-assignment receipt was supplied",
        }
    if receipt.get("schema") != 3 or receipt.get("evidence_kind") != "live_native":
        raise ValueError("candidate receipt is not live native schema 3 evidence")
    if receipt.get("contract_schema") != contract["schema"]:
        raise ValueError("candidate receipt targets a different contract schema")
    if not isinstance(receipt.get("codex_version"), str) or not receipt["codex_version"]:
        raise ValueError("candidate receipt is missing Codex version")
    source_commit = receipt.get("source_commit")
    if not isinstance(source_commit, str) or GIT_OID.fullmatch(source_commit) is None:
        raise ValueError("candidate receipt has an invalid source commit")

    runtime = receipt.get("runtime")
    if not isinstance(runtime, dict) or set(REQUIRED_RUNTIME_FIELDS) - set(runtime):
        raise ValueError("candidate receipt is missing runtime provenance")
    for key in ("candidate_binary_sha256", "candidate_patch_sha256"):
        if not isinstance(runtime.get(key), str) or SHA256.fullmatch(runtime[key]) is None:
            raise ValueError(f"candidate runtime {key} is invalid")
    selected_executable = runtime.get("selected_executable")
    if (
        not isinstance(selected_executable, str)
        or ABSOLUTE_EXECUTABLE.match(selected_executable) is None
    ):
        raise ValueError("candidate selected executable is not absolute")
    if runtime.get("selection_mechanism") != "direct_executable":
        raise ValueError("candidate selection mechanism is invalid")
    if runtime.get("signed_app_resource_replaced") is not False:
        raise ValueError("candidate receipt replaced the signed Codex app resource")
    if runtime.get("headless_only") is not True:
        raise ValueError("candidate receipt is not headless-only")
    if runtime.get("gui_app_server_selected") is not False:
        raise ValueError("candidate receipt selected the GUI app server")

    config = receipt.get("configuration")
    if not isinstance(config, dict):
        raise ValueError("candidate receipt is missing configuration")
    expected_config = {
        "default_message_delivery": "encrypted",
        "active_message_delivery": "plaintext",
        "explicit_opt_in": True,
        "parent_provider": "openai",
        "parent_auth_unchanged": True,
        "parent_base_url_unchanged": True,
        "live_config_modified": False,
        "native_multi_agent_v2": True,
        "tool_namespace": contract["required_tool_namespace"],
        "configured_plaintext_operations": sorted(REQUIRED_OPERATIONS),
        "null_marker_plaintext_requires_exact_route": True,
        "unconfigured_null_marker_remains_encrypted": True,
    }
    if any(config.get(key) != expected for key, expected in expected_config.items()):
        raise ValueError("candidate configuration violates the transport boundary")

    operations = receipt.get("operations")
    if not isinstance(operations, list) or any(
        not isinstance(operation, dict) for operation in operations
    ):
        raise ValueError("candidate receipt operations are invalid")
    by_id = {operation.get("id"): operation for operation in operations}
    if len(by_id) != len(operations) or set(by_id) != REQUIRED_OPERATIONS:
        raise ValueError("candidate receipt operations are incomplete or duplicated")

    hook_names = contract["required_hook_tool_names"]
    for operation_id, operation in by_id.items():
        if operation.get("hook_tool_name") != hook_names[operation_id]:
            raise ValueError(f"{operation_id} Hook tool identity is not exact")
        if set(operation) - {"id", "hook_tool_name", "delivery_case", "deny_case"}:
            raise ValueError(f"{operation_id} contains ambiguous unpaired evidence")
        if set(REQUIRED_CASES) - set(operation):
            raise ValueError(f"{operation_id} is missing a delivery or deny case")

        delivery = operation["delivery_case"]
        deny = operation["deny_case"]
        if not isinstance(delivery, dict) or not isinstance(deny, dict):
            raise ValueError(f"{operation_id} paired cases are invalid")
        delivery_identity = _call_identity(
            delivery.get("call_identity"), f"{operation_id} delivery", delivery=True
        )
        deny_identity = _call_identity(
            deny.get("call_identity"), f"{operation_id} deny", delivery=False
        )
        if delivery_identity["tool_use_id"] == deny_identity["tool_use_id"]:
            raise ValueError(f"{operation_id} delivery and deny must be distinct calls")
        if operation_id == "spawn_agent":
            task_name = delivery_identity.get("requested_task_name")
            if not isinstance(task_name, str) or TASK_NAME.fullmatch(task_name) is None:
                raise ValueError("spawn_agent delivery requested task name is invalid")
            if deny_identity.get("requested_task_name") != task_name:
                raise ValueError("spawn_agent paired task names are not exact")

        if delivery.get("schema_message_encrypted") is not False:
            raise ValueError(f"{operation_id} message schema is still encrypted")
        _plaintext_route(
            delivery.get("plaintext_route"), operation_id, f"{operation_id} delivery", contract
        )
        pretool = _fingerprint(
            delivery.get("pretool_plaintext"), f"{operation_id} delivery PreToolUse"
        )
        handler = _fingerprint(delivery.get("handler_plaintext"), f"{operation_id} handler")
        delivered = _fingerprint(
            delivery.get("delivered_plaintext"), f"{operation_id} recipient"
        )
        if not (pretool == handler == delivered):
            raise ValueError(f"{operation_id} plaintext bytes are not end-to-end identical")
        if delivery.get("encrypted_content_present") is not False:
            raise ValueError(f"{operation_id} delivery retained encrypted content")
        if delivery.get("hook_before_handler") is not True:
            raise ValueError(f"{operation_id} Hook ordering is not proven")
        if delivery.get("native_multi_agent_v2") is not True:
            raise ValueError(f"{operation_id} bypassed native Multi-Agent V2")
        deny_pretool = _fingerprint(
            deny.get("pretool_plaintext"), f"{operation_id} deny PreToolUse"
        )
        if deny_pretool != pretool:
            raise ValueError(f"{operation_id} paired calls did not use exact message bytes")
        if deny.get("schema_message_encrypted") is not False:
            raise ValueError(f"{operation_id} deny message schema is still encrypted")
        _plaintext_route(
            deny.get("plaintext_route"), operation_id, f"{operation_id} deny", contract
        )
        if deny.get("native_multi_agent_v2") is not True:
            raise ValueError(f"{operation_id} deny call bypassed native Multi-Agent V2")
        if deny.get("blocked_before_handler") is not True:
            raise ValueError(f"{operation_id} deny control did not block before dispatch")
        if deny.get("handler_started") is not False:
            raise ValueError(f"{operation_id} deny control allowed handler dispatch")
        if deny.get("recipient_started") is not False:
            raise ValueError(f"{operation_id} deny control allowed recipient execution")

    regressions = receipt.get("regressions")
    expected_regressions = {
        "encrypted_mode_still_encrypted": True,
        "unconfigured_null_marker_still_encrypted": True,
        "nonempty_private_marker_fails_closed": True,
        "v1_fallback_used": False,
        "native_agent_control_preserved": True,
    }
    if not isinstance(regressions, dict) or any(
        regressions.get(key) != expected
        for key, expected in expected_regressions.items()
    ):
        raise ValueError("candidate receipt is missing required regressions")

    privacy = receipt.get("privacy")
    if not isinstance(privacy, dict) or privacy.get("raw_plaintext_stored") is not False:
        raise ValueError("candidate receipt stored raw plaintext")
    if privacy.get("credential_value_read_or_stored") is not False:
        raise ValueError("candidate receipt accessed a credential value")

    return {
        "receipt_valid": True,
        "plaintext_assignment_seam_qualified": True,
        "phase1_complete": False,
        "direct_write_qualified": False,
        "blocker": None,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--contract",
        type=Path,
        default=Path(__file__).with_name("native-plaintext-assignment-seam-contract.json"),
    )
    parser.add_argument("--receipt", type=Path)
    parser.add_argument("--require-qualified", action="store_true")
    args = parser.parse_args()

    try:
        contract = load_contract(args.contract)
        receipt = (
            json.loads(args.receipt.read_text(encoding="utf-8"))
            if args.receipt is not None
            else None
        )
        result = assess(contract, receipt)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        print(json.dumps({"valid": False, "error": str(exc)}, separators=(",", ":")))
        return 1

    result["valid"] = True
    result["contract_schema"] = contract["schema"]
    print(json.dumps(result, ensure_ascii=False, separators=(",", ":")))
    if args.require_qualified and not result["plaintext_assignment_seam_qualified"]:
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
