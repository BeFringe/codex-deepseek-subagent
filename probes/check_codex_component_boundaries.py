#!/usr/bin/env python3

import argparse
import json
from pathlib import Path
import re
import subprocess
import sys


PROBE_DIRECTORY = Path(__file__).resolve().parent
if str(PROBE_DIRECTORY) not in sys.path:
    sys.path.insert(0, str(PROBE_DIRECTORY))

from check_runtime_evidence_index import (  # noqa: E402
    DEFAULT_INDEX,
    evidence_path,
    load_index,
    runtime_identity,
)


GIT_OID = re.compile(r"^[0-9a-f]{40}$")
REQUIRED_COMPONENTS = {"cli_core", "typescript_sdk", "python_sdk", "app_server"}
REQUIRED_ANCHORS = {
    "bounded_role_overrides",
    "parent_provider_preserved",
    "v2_message_schema_encrypted",
    "plaintext_response_item_discriminator",
    "plaintext_child_message_branch",
    "typescript_sdk_exec_driver",
    "python_sdk_app_server_driver",
    "app_server_thread_provider_parameter",
    "app_server_thread_source_separate_from_session_source",
    "app_server_root_start_has_no_parent",
    "app_server_child_direct_input_rejected",
    "app_server_has_no_native_spawn_rpc",
}
REQUIRED_VERDICT = {
    "source_visibility_improved": True,
    "isolated_probe_harness_feasible": True,
    "native_heterogeneous_child_restored": False,
    "pretool_plaintext_assignment_visible": False,
    "per_child_provider_override_available": False,
    "app_server_thread_is_native_child_equivalent": False,
    "phase1_complete": False,
    "direct_write_qualified": False,
    "phase2_state": "closed",
    "phase3_state": "closed",
}


def load_contract(path):
    value = json.loads(path.read_text(encoding="utf-8"))
    if value.get("schema") != 1:
        raise ValueError("component boundary contract has an invalid schema")
    if not isinstance(value.get("codex_version"), str) or not value["codex_version"]:
        raise ValueError("component boundary contract has no exact Codex version")
    if GIT_OID.fullmatch(str(value.get("source_commit", ""))) is None:
        raise ValueError("component boundary contract has an invalid source commit")

    components = value.get("components")
    if not isinstance(components, dict) or set(components) != REQUIRED_COMPONENTS:
        raise ValueError("component boundary contract has an incomplete component set")

    anchors = value.get("anchors")
    if not isinstance(anchors, list) or any(not isinstance(item, dict) for item in anchors):
        raise ValueError("component boundary anchors must be a list of objects")
    by_id = {item.get("id"): item for item in anchors}
    if len(by_id) != len(anchors) or set(by_id) != REQUIRED_ANCHORS:
        raise ValueError("component boundary anchor ids are incomplete or duplicated")
    for item in anchors:
        if not all(
            isinstance(item.get(key), str) and item[key]
            for key in ("path", "contains")
        ):
            raise ValueError(f"component boundary anchor {item.get('id')} is invalid")
        forbidden = item.get("not_contains")
        if forbidden is not None and (not isinstance(forbidden, str) or not forbidden):
            raise ValueError(
                f"component boundary anchor {item.get('id')} has an invalid negative value"
            )

    verdict = value.get("verdict")
    if not isinstance(verdict, dict):
        raise ValueError("component boundary contract is missing its verdict")
    for key, expected in REQUIRED_VERDICT.items():
        if verdict.get(key) != expected:
            raise ValueError(f"component boundary verdict cannot promote {key}")
    if not isinstance(verdict.get("blocker"), str) or not verdict["blocker"]:
        raise ValueError("component boundary verdict is missing its blocker")
    return value


def _git_identity(source_root):
    try:
        requested = source_root.resolve(strict=True)
    except OSError as error:
        return None, None, [f"cannot resolve source root: {error}"]

    values = {}
    failures = []
    for label, args in {
        "root": ["rev-parse", "--show-toplevel"],
        "head": ["rev-parse", "--verify", "HEAD^{commit}"],
    }.items():
        result = subprocess.run(
            ["git", "-C", str(requested), *args],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        if result.returncode != 0:
            failures.append(f"cannot resolve source {label}")
        else:
            values[label] = result.stdout.strip()
    root = values.get("root")
    if root is not None and Path(root).resolve() != requested:
        failures.append("source path is not the exact Git top level")
    return requested, values.get("head"), failures


def verify_source(contract, source_root):
    root, head, failures = _git_identity(source_root)
    if head is not None and head != contract["source_commit"]:
        failures.append(
            "Codex source HEAD drifted: "
            f"expected={contract['source_commit']} actual={head}"
        )
    if root is None or failures:
        return head, failures

    for anchor in contract["anchors"]:
        try:
            source = (root / anchor["path"]).read_text(encoding="utf-8")
        except OSError as error:
            failures.append(f"cannot read {anchor['path']}: {error}")
            continue
        if anchor["contains"] not in source:
            failures.append(f"source anchor drifted: {anchor['id']}")
        forbidden = anchor.get("not_contains")
        if forbidden is not None and forbidden in source:
            failures.append(f"forbidden source anchor found: {anchor['id']}")
    return head, failures


def qualification(contract):
    verdict = contract["verdict"]
    return {key: verdict[key] for key in (*REQUIRED_VERDICT, "blocker")}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--contract",
        type=Path,
    )
    parser.add_argument("--release-index", type=Path, default=DEFAULT_INDEX)
    parser.add_argument("--codex-source", type=Path, required=True)
    parser.add_argument("--require-native-heterogeneous-child", action="store_true")
    args = parser.parse_args()

    try:
        index = load_index(args.release_index)
        identity = runtime_identity(index)
        contract_path = args.contract or evidence_path(index, "component_boundaries")
        contract = load_contract(contract_path)
        if any(contract[key] != identity[key] for key in ("codex_version", "source_commit")):
            raise ValueError(
                "component boundary identity disagrees with the current runtime role"
            )
        observed_head, failures = verify_source(contract, args.codex_source)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
        print(json.dumps({"valid": False, "error": str(error)}, separators=(",", ":")))
        return 1

    result = qualification(contract)
    result.update(
        {
            "valid": not failures,
            "runtime_role": index["current_runtime_role"],
            "codex_version": contract["codex_version"],
            "source_commit": contract["source_commit"],
            "observed_source_head": observed_head,
            "source_failures": failures,
        }
    )
    print(json.dumps(result, ensure_ascii=False, separators=(",", ":")))
    if failures:
        return 1
    if args.require_native_heterogeneous_child and not result[
        "native_heterogeneous_child_restored"
    ]:
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
