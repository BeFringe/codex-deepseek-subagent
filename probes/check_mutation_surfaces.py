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


SCHEMA_1_REQUIRED_SURFACES = {
    "shell",
    "write_stdin",
    "apply_patch",
    "mcp",
    "code_mode",
    "extension_freeform",
    "dynamic_function",
    "agent_control",
}
SCHEMA_2_REQUIRED_SURFACES = SCHEMA_1_REQUIRED_SURFACES | {
    "extension_function",
    "codex_config_mutation",
    "authority_escalation",
    "tool_search",
    "hosted_model_tool",
}
SCHEMA_3_REQUIRED_SURFACES = SCHEMA_2_REQUIRED_SURFACES | {
    "plugin_metrics_sidecar",
    "accepted_result_evidence",
}
SCHEMA_4_REQUIRED_SURFACES = SCHEMA_3_REQUIRED_SURFACES | {
    "appserver_host_control_bootstrap",
}
REQUIRED_SURFACES_BY_SCHEMA = {
    1: SCHEMA_1_REQUIRED_SURFACES,
    2: SCHEMA_2_REQUIRED_SURFACES,
    3: SCHEMA_3_REQUIRED_SURFACES,
    4: SCHEMA_4_REQUIRED_SURFACES,
}
QUALIFIED_DECISIONS = {"candidate-covered"}
GIT_OID = re.compile(r"^(?:[0-9a-f]{40}|[0-9a-f]{64})$")


def load_matrix(path):
    value = json.loads(path.read_text(encoding="utf-8"))
    required_surfaces = REQUIRED_SURFACES_BY_SCHEMA.get(value.get("schema"))
    if required_surfaces is None or not isinstance(value.get("surfaces"), list):
        raise ValueError("mutation matrix has an invalid schema")
    by_id = {surface.get("id"): surface for surface in value["surfaces"]}
    if len(by_id) != len(value["surfaces"]):
        raise ValueError("mutation matrix contains duplicate surface ids")
    if set(by_id) != required_surfaces:
        missing = sorted(required_surfaces - set(by_id))
        extra = sorted(set(by_id) - required_surfaces)
        raise ValueError(f"mutation matrix surface mismatch: missing={missing}, extra={extra}")
    if not isinstance(value.get("codex_version"), str) or not value["codex_version"]:
        raise ValueError("mutation matrix has no Codex version")
    source_commit = value.get("source_commit")
    if not isinstance(source_commit, str) or GIT_OID.fullmatch(source_commit) is None:
        raise ValueError("mutation matrix has an invalid source commit")
    return value


def verify_source_identity(matrix, source_root):
    failures = []
    try:
        requested = source_root.resolve(strict=True)
    except OSError as error:
        return [f"cannot resolve Codex source root: {error}"]
    commands = {
        "root": ["git", "-C", str(requested), "rev-parse", "--show-toplevel"],
        "head": ["git", "-C", str(requested), "rev-parse", "--verify", "HEAD^{commit}"],
    }
    results = {}
    for label, command in commands.items():
        result = subprocess.run(
            command,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        if result.returncode != 0:
            failures.append(f"cannot resolve Codex source {label}")
            continue
        results[label] = result.stdout.strip()
    root = results.get("root")
    if root is not None and Path(root).resolve() != requested:
        failures.append("Codex source path is not the exact Git top level")
    head = results.get("head")
    if head is not None and head != matrix["source_commit"]:
        failures.append(
            "Codex source HEAD does not match matrix source_commit: "
            f"expected={matrix['source_commit']} actual={head}"
        )
    return failures


def verify_anchors(matrix, source_root):
    failures = []
    for surface in matrix["surfaces"]:
        for anchor in surface.get("anchors", []):
            path = source_root / anchor["path"]
            try:
                text = path.read_text(encoding="utf-8")
            except OSError as error:
                failures.append(f"{surface['id']}: cannot read {anchor['path']}: {error}")
                continue
            if anchor["contains"] not in text:
                failures.append(
                    f"{surface['id']}: source anchor drifted in {anchor['path']}: {anchor['contains']!r}"
                )
    return failures


def qualification(matrix):
    blockers = []
    for surface in matrix["surfaces"]:
        if not surface.get("mutation_capable"):
            continue
        if surface.get("decision") not in QUALIFIED_DECISIONS:
            blockers.append(
                {
                    "id": surface["id"],
                    "decision": surface.get("decision"),
                    "negative_space": surface.get("negative_space"),
                }
            )
    return {"direct_write_qualified": not blockers, "blockers": blockers}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--matrix", type=Path)
    parser.add_argument("--release-index", type=Path, default=DEFAULT_INDEX)
    parser.add_argument("--codex-source", type=Path)
    parser.add_argument("--require-qualified", action="store_true")
    arguments = parser.parse_args()

    try:
        index = load_index(arguments.release_index)
        identity = runtime_identity(index)
        matrix_path = arguments.matrix or evidence_path(index, "mutation_surfaces")
        matrix = load_matrix(matrix_path)
        if arguments.matrix is None and any(
            matrix[key] != identity[key] for key in ("codex_version", "source_commit")
        ):
            raise ValueError(
                "default mutation matrix identity disagrees with the current runtime role"
            )
        source_identity_failures = (
            verify_source_identity(matrix, arguments.codex_source)
            if arguments.codex_source
            else []
        )
        anchor_failures = (
            verify_anchors(matrix, arguments.codex_source.resolve())
            if arguments.codex_source and not source_identity_failures
            else []
        )
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
        print(json.dumps({"valid": False, "error": str(error)}, separators=(",", ":")))
        return 1

    result = qualification(matrix)
    result.update(
        {
            "valid": not source_identity_failures and not anchor_failures,
            "runtime_role": (
                index["current_runtime_role"] if arguments.matrix is None else None
            ),
            "codex_version": matrix["codex_version"],
            "source_commit": matrix["source_commit"],
            "source_identity_verified": bool(arguments.codex_source)
            and not source_identity_failures,
            "source_identity_failures": source_identity_failures,
            "anchor_failures": anchor_failures,
        }
    )
    print(json.dumps(result, ensure_ascii=False, separators=(",", ":")))
    if source_identity_failures or anchor_failures:
        return 1
    if arguments.require_qualified and not result["direct_write_qualified"]:
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
