#!/usr/bin/env python3

import argparse
import json
from pathlib import Path
import sys


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
REQUIRED_SURFACES_BY_SCHEMA = {
    1: SCHEMA_1_REQUIRED_SURFACES,
    2: SCHEMA_2_REQUIRED_SURFACES,
}
QUALIFIED_DECISIONS = {"candidate-covered"}


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
    return value


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
    default_matrix = Path(__file__).with_name(
        "codex-0.148.0-alpha.9-mutation-surfaces.json"
    )
    parser = argparse.ArgumentParser()
    parser.add_argument("--matrix", type=Path, default=default_matrix)
    parser.add_argument("--codex-source", type=Path)
    parser.add_argument("--require-qualified", action="store_true")
    arguments = parser.parse_args()

    try:
        matrix = load_matrix(arguments.matrix)
        anchor_failures = (
            verify_anchors(matrix, arguments.codex_source.resolve())
            if arguments.codex_source
            else []
        )
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
        print(json.dumps({"valid": False, "error": str(error)}, separators=(",", ":")))
        return 1

    result = qualification(matrix)
    result.update(
        {
            "valid": not anchor_failures,
            "codex_version": matrix["codex_version"],
            "source_commit": matrix["source_commit"],
            "anchor_failures": anchor_failures,
        }
    )
    print(json.dumps(result, ensure_ascii=False, separators=(",", ":")))
    if anchor_failures:
        return 1
    if arguments.require_qualified and not result["direct_write_qualified"]:
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
