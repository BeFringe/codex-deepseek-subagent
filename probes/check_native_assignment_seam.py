#!/usr/bin/env python3

import argparse
import json
from pathlib import Path
import subprocess
import sys


REQUIRED_ANCHORS = {
    "function_call_private_metadata",
    "v2_spawn_message_schema_encrypted",
    "v2_encryption_regression_fixture",
    "plaintext_source_discriminator",
    "hook_input_from_arguments",
    "pretool_before_handler",
    "spawn_handler_reads_message",
    "non_plaintext_becomes_encrypted_content",
    "child_request_preserves_encrypted_content",
    "encrypted_and_plaintext_integration_fixture",
}
REQUIRED_ORDER_CHECKS = {
    "pretool_before_handler",
    "message_before_transport_wrap",
    "transport_wrap_before_child_model_input",
}


def load_contract(path):
    value = json.loads(path.read_text(encoding="utf-8"))
    if value.get("schema") != 1:
        raise ValueError("assignment seam contract has an invalid schema")
    if not isinstance(value.get("source_commit"), str) or not value["source_commit"]:
        raise ValueError("assignment seam contract is missing source_commit")

    anchors = value.get("anchors")
    if not isinstance(anchors, list) or any(not isinstance(item, dict) for item in anchors):
        raise ValueError("assignment seam anchors must be a list of objects")
    by_id = {item.get("id"): item for item in anchors}
    if len(by_id) != len(anchors) or set(by_id) != REQUIRED_ANCHORS:
        raise ValueError("assignment seam anchor ids are incomplete or duplicated")
    for item in anchors:
        if not all(isinstance(item.get(key), str) and item[key] for key in ("path", "contains")):
            raise ValueError(f"assignment seam anchor {item.get('id')} is invalid")

    order_checks = value.get("order_checks")
    if not isinstance(order_checks, list) or any(
        not isinstance(item, dict) for item in order_checks
    ):
        raise ValueError("assignment seam order checks must be a list of objects")
    order_by_id = {item.get("id"): item for item in order_checks}
    if len(order_by_id) != len(order_checks) or set(order_by_id) != REQUIRED_ORDER_CHECKS:
        raise ValueError("assignment seam order-check ids are incomplete or duplicated")
    for item in order_checks:
        if not all(
            isinstance(item.get(key), str) and item[key]
            for key in ("path", "before", "after")
        ):
            raise ValueError(f"assignment seam order check {item.get('id')} is invalid")

    verdict = value.get("verdict")
    if not isinstance(verdict, dict):
        raise ValueError("assignment seam contract is missing verdict")
    if verdict.get("pretool_plaintext_assignment_visible") is not False:
        raise ValueError("current assignment seam must remain fail closed")
    if verdict.get("phase1_complete") is not False:
        raise ValueError("assignment seam contract cannot complete Phase 1")
    if verdict.get("direct_write_qualified") is not False:
        raise ValueError("assignment seam contract cannot qualify direct write")
    return value


def _git_head(source_root):
    result = subprocess.run(
        ["git", "-C", str(source_root), "rev-parse", "HEAD"],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if result.returncode != 0:
        return None, result.stderr.strip() or "git rev-parse failed"
    return result.stdout.strip(), None


def verify_source(contract, source_root):
    failures = []
    head, error = _git_head(source_root)
    if error:
        failures.append(f"cannot resolve Codex source HEAD: {error}")
    elif head != contract["source_commit"]:
        failures.append(
            f"Codex source HEAD drifted: expected {contract['source_commit']}, observed {head}"
        )

    text_by_path = {}
    for item in [*contract["anchors"], *contract["order_checks"]]:
        relative = item["path"]
        if relative in text_by_path:
            continue
        try:
            text_by_path[relative] = (source_root / relative).read_text(encoding="utf-8")
        except OSError as exc:
            failures.append(f"cannot read {relative}: {exc}")

    for anchor in contract["anchors"]:
        text = text_by_path.get(anchor["path"])
        if text is not None and anchor["contains"] not in text:
            failures.append(f"source anchor drifted: {anchor['id']}")

    for check in contract["order_checks"]:
        text = text_by_path.get(check["path"])
        if text is None:
            continue
        before = text.find(check["before"])
        after = text.find(check["after"])
        if before < 0 or after < 0 or before >= after:
            failures.append(f"source order drifted: {check['id']}")
    return head, failures


def qualification(contract):
    verdict = contract["verdict"]
    return {
        "plaintext_assignment_seam_qualified": verdict[
            "pretool_plaintext_assignment_visible"
        ],
        "phase1_complete": verdict["phase1_complete"],
        "direct_write_qualified": verdict["direct_write_qualified"],
        "blocker": verdict["blocker"],
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--contract",
        type=Path,
        default=Path(__file__).with_name(
            "codex-0.148.0-alpha.9-native-assignment-seam.json"
        ),
    )
    parser.add_argument("--codex-source", type=Path, required=True)
    parser.add_argument("--require-plaintext-seam", action="store_true")
    args = parser.parse_args()

    try:
        contract = load_contract(args.contract)
        observed_head, failures = verify_source(contract, args.codex_source.resolve())
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        print(json.dumps({"valid": False, "error": str(exc)}, separators=(",", ":")))
        return 1

    result = qualification(contract)
    result.update(
        {
            "valid": not failures,
            "codex_version": contract["codex_version"],
            "source_commit": contract["source_commit"],
            "observed_source_head": observed_head,
            "anchor_failures": failures,
        }
    )
    print(json.dumps(result, ensure_ascii=False, separators=(",", ":")))
    if failures:
        return 1
    if args.require_plaintext_seam and not result["plaintext_assignment_seam_qualified"]:
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
