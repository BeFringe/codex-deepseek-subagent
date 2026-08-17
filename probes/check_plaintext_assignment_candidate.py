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
    "exact_pretool_plaintext",
    "deny_before_dispatch",
    "exact_delivered_bytes",
    "native_multi_agent_v2_preserved",
    "private_branch_fails_closed",
    "encrypted_mode_regression",
    "openai_parent_unchanged",
    "evidence_redacted",
}
SHA256 = re.compile(r"^[0-9a-f]{64}$")
GIT_OID = re.compile(r"^[0-9a-f]{40}$|^[0-9a-f]{64}$")


def load_contract(path):
    value = json.loads(path.read_text(encoding="utf-8"))
    if value.get("schema") != 1:
        raise ValueError("plaintext assignment contract has an invalid schema")
    if set(value.get("required_operations", [])) != REQUIRED_OPERATIONS:
        raise ValueError("plaintext assignment contract has incomplete operations")
    if set(value.get("required_invariants", [])) != REQUIRED_INVARIANTS:
        raise ValueError("plaintext assignment contract has incomplete invariants")
    if value.get("default_mode") != "encrypted":
        raise ValueError("plaintext assignment transport must remain opt-in")
    if value.get("qualification_mode") != "plaintext":
        raise ValueError("plaintext assignment qualification mode is invalid")

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


def assess(contract, receipt):
    if receipt is None:
        return {
            "receipt_valid": False,
            "plaintext_assignment_seam_qualified": False,
            "phase1_complete": False,
            "direct_write_qualified": False,
            "blocker": "no live native plaintext-assignment receipt was supplied",
        }
    if receipt.get("schema") != 1 or receipt.get("evidence_kind") != "live_native":
        raise ValueError("candidate receipt is not live native schema 1 evidence")
    if receipt.get("contract_schema") != contract["schema"]:
        raise ValueError("candidate receipt targets a different contract schema")
    if not isinstance(receipt.get("codex_version"), str) or not receipt["codex_version"]:
        raise ValueError("candidate receipt is missing Codex version")
    source_commit = receipt.get("source_commit")
    if not isinstance(source_commit, str) or GIT_OID.fullmatch(source_commit) is None:
        raise ValueError("candidate receipt has an invalid source commit")

    config = receipt.get("configuration")
    if not isinstance(config, dict):
        raise ValueError("candidate receipt is missing configuration")
    expected_config = {
        "default_message_delivery": "encrypted",
        "active_message_delivery": "plaintext",
        "explicit_opt_in": True,
        "parent_provider": "openai",
        "parent_auth_unchanged": True,
        "native_multi_agent_v2": True,
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
        if operation.get("schema_message_encrypted") is not False:
            raise ValueError(f"{operation_id} message schema is still encrypted")
        if operation.get("function_call_encrypted_function_args") != []:
            raise ValueError(f"{operation_id} did not select the plaintext response branch")
        pretool = _fingerprint(operation.get("pretool_plaintext"), f"{operation_id} PreToolUse")
        handler = _fingerprint(operation.get("handler_plaintext"), f"{operation_id} handler")
        delivered = _fingerprint(
            operation.get("delivered_plaintext"), f"{operation_id} delivery"
        )
        if not (pretool == handler == delivered):
            raise ValueError(f"{operation_id} plaintext bytes are not end-to-end identical")
        if operation.get("encrypted_content_present") is not False:
            raise ValueError(f"{operation_id} delivery retained encrypted content")
        if operation.get("hook_before_handler") is not True:
            raise ValueError(f"{operation_id} Hook ordering is not proven")
        if operation.get("native_multi_agent_v2") is not True:
            raise ValueError(f"{operation_id} bypassed native Multi-Agent V2")
        canonical_path = operation.get("canonical_agent_path")
        if not isinstance(canonical_path, str) or not canonical_path.startswith("/"):
            raise ValueError(f"{operation_id} canonical AgentPath is invalid")
        deny = operation.get("deny_control")
        if not isinstance(deny, dict) or deny.get("blocked_before_handler") is not True:
            raise ValueError(f"{operation_id} deny control did not block before dispatch")
        if deny.get("recipient_started") is not False:
            raise ValueError(f"{operation_id} deny control allowed recipient execution")

    regressions = receipt.get("regressions")
    expected_regressions = {
        "encrypted_mode_still_encrypted": True,
        "private_marker_missing_fails_closed": True,
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
