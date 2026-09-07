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
EXPECTED_FAMILIES = {
    "filesystem": {
        "fs/writeFile",
        "fs/createDirectory",
        "fs/remove",
        "fs/copy",
    },
    "command": {"command/exec", "command/exec/write", "command/exec/terminate"},
    "process": {"process/spawn", "process/writeStdin", "process/kill"},
}
EXPECTED_FAMILY_METADATA = {
    "filesystem": ("sandbox_none", "concurrent"),
    "command": ("server_sandbox", "connection_or_process_id"),
    "process": ("no_codex_sandbox", "connection_or_process_handle"),
}
EXPECTED_BOUNDARY = {
    "requester_authority": "app_server_client_connection",
    "native_child_tool_surface": False,
    "thread_identity_required": False,
    "pretooluse_child_mediation_qualified": False,
    "same_uid_client_reachability": "unproven",
}
EXPECTED_VERDICT = {
    "host_control_mutation_surface_visible": True,
    "native_child_reachability_proven": False,
    "pretooluse_child_mediation_proven": False,
    "same_uid_client_trust_proven": False,
    "may_count_as_child_mutation_qualification": False,
    "isolated_client_trust_probe_required": True,
    "phase1_complete": False,
    "direct_write_qualified": False,
}
EXPECTED_ANCHORS = {
    "filesystem_requests_are_concurrent",
    "filesystem_write_rpc",
    "filesystem_create_directory_rpc",
    "filesystem_remove_rpc",
    "filesystem_copy_rpc",
    "filesystem_write_has_no_sandbox",
    "command_exec_uses_server_sandbox",
    "command_exec_write_rpc",
    "command_exec_terminate_rpc",
    "process_spawn_has_no_codex_sandbox",
    "process_write_stdin_rpc",
    "process_kill_rpc",
    "filesystem_params_have_no_thread_identity",
    "process_params_have_no_thread_identity",
    "command_params_have_no_thread_identity",
}


def load_contract(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if value.get("schema") != 1:
        raise ValueError("App Server host-control contract has an invalid schema")
    if not isinstance(value.get("codex_version"), str) or not value["codex_version"]:
        raise ValueError("App Server host-control contract has no exact Codex version")
    if GIT_OID.fullmatch(str(value.get("source_commit", ""))) is None:
        raise ValueError("App Server host-control source commit is invalid")
    if value.get("boundary") != EXPECTED_BOUNDARY:
        raise ValueError("App Server host-control boundary drifted or was promoted")

    families = value.get("families")
    if not isinstance(families, dict) or set(families) != set(EXPECTED_FAMILIES):
        raise ValueError("App Server host-control family set is incomplete")
    for family_id, expected_methods in EXPECTED_FAMILIES.items():
        family = families[family_id]
        if not isinstance(family, dict) or set(family) != {
            "methods",
            "execution_confinement",
            "serialization",
            "worker_reachability",
            "decision",
        }:
            raise ValueError(f"App Server host-control {family_id} fields are not exact")
        if set(family.get("methods", [])) != expected_methods:
            raise ValueError(f"App Server host-control {family_id} methods are incomplete")
        expected_confinement, expected_serialization = EXPECTED_FAMILY_METADATA[family_id]
        if family.get("execution_confinement") != expected_confinement:
            raise ValueError(f"App Server host-control {family_id} confinement drifted")
        if family.get("serialization") != expected_serialization:
            raise ValueError(f"App Server host-control {family_id} serialization drifted")
        if family.get("worker_reachability") != "unproven":
            raise ValueError(f"App Server host-control {family_id} reachability was promoted")
        if family.get("decision") != "host-control-only-unqualified":
            raise ValueError(f"App Server host-control {family_id} decision drifted")

    anchors = value.get("anchors")
    if not isinstance(anchors, list) or any(not isinstance(item, dict) for item in anchors):
        raise ValueError("App Server host-control anchors are invalid")
    by_id = {item.get("id"): item for item in anchors}
    if len(by_id) != len(anchors) or set(by_id) != EXPECTED_ANCHORS:
        raise ValueError("App Server host-control anchors are incomplete or duplicated")
    for item in anchors:
        if not all(isinstance(item.get(key), str) and item[key] for key in ("path", "contains")):
            raise ValueError(f"App Server host-control anchor {item.get('id')} is invalid")
        forbidden = item.get("not_contains")
        if forbidden is not None and (not isinstance(forbidden, str) or not forbidden):
            raise ValueError(f"App Server host-control anchor {item.get('id')} has invalid negative text")

    verdict = value.get("verdict")
    if not isinstance(verdict, dict):
        raise ValueError("App Server host-control verdict is missing")
    for key, expected in EXPECTED_VERDICT.items():
        if verdict.get(key) != expected:
            raise ValueError(f"App Server host-control verdict cannot promote {key}")
    return value


def _git_identity(source_root: Path) -> tuple[Path | None, str | None, list[str]]:
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
    if values.get("root") is not None and Path(values["root"]).resolve() != requested:
        failures.append("source path is not the exact Git top level")
    return requested, values.get("head"), failures


def verify_source(contract: dict, source_root: Path) -> tuple[str | None, list[str]]:
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


def qualification(contract: dict) -> dict:
    return dict(contract["verdict"])


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--contract",
        type=Path,
    )
    parser.add_argument("--release-index", type=Path, default=DEFAULT_INDEX)
    parser.add_argument("--codex-source", type=Path, required=True)
    parser.add_argument("--require-child-mediated", action="store_true")
    args = parser.parse_args()
    try:
        index = load_index(args.release_index)
        identity = runtime_identity(index)
        contract_path = args.contract or evidence_path(index, "appserver_host_control")
        contract = load_contract(contract_path)
        if any(contract[key] != identity[key] for key in ("codex_version", "source_commit")):
            raise ValueError(
                "App Server host-control identity disagrees with the current runtime role"
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
    if args.require_child_mediated and not result["may_count_as_child_mutation_qualification"]:
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
