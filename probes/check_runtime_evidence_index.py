#!/usr/bin/env python3

"""Resolve semantic Codex runtime roles to immutable evidence artifacts."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys


GIT_OID = re.compile(r"^[0-9a-f]{40}$")
REQUIRED_RUNTIME_ROLES = {
    "migration_handoff_runtime",
    "schema_replay_runtime",
    "prior_signed_runtime",
    "current_signed_runtime",
}
REQUIRED_CURRENT_EVIDENCE = {
    "component_boundaries",
    "native_assignment_seam",
    "lifecycle_sources",
    "mutation_surfaces",
    "appserver_host_control",
    "installed_baseline",
}
DEFAULT_INDEX = Path(__file__).with_name("codex-runtime-evidence-index.json")
REPO_ROOT = Path(__file__).resolve().parents[1]


def _role_list(value: object, roles: dict, label: str) -> tuple[str, ...]:
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise ValueError(f"{label} must be a list of semantic runtime roles")
    if len(value) != len(set(value)) or any(item not in roles for item in value):
        raise ValueError(f"{label} contains a duplicate or unknown runtime role")
    return tuple(value)


def load_index(path: Path = DEFAULT_INDEX) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if value.get("schema") != 1:
        raise ValueError("runtime evidence index has an invalid schema")
    roles = value.get("runtime_roles")
    if not isinstance(roles, dict) or set(roles) != REQUIRED_RUNTIME_ROLES:
        raise ValueError("runtime evidence index has an incomplete semantic role set")
    identities = set()
    for role, identity in roles.items():
        if not isinstance(identity, dict) or set(identity) != {
            "codex_version",
            "source_commit",
        }:
            raise ValueError(f"runtime role {role} has invalid identity fields")
        version = identity.get("codex_version")
        source_commit = identity.get("source_commit")
        if not isinstance(version, str) or not version:
            raise ValueError(f"runtime role {role} has no exact Codex version")
        if not isinstance(source_commit, str) or GIT_OID.fullmatch(source_commit) is None:
            raise ValueError(f"runtime role {role} has an invalid source commit")
        pair = (version, source_commit)
        if pair in identities:
            raise ValueError("two semantic runtime roles resolve to the same identity")
        identities.add(pair)

    current_role = value.get("current_runtime_role")
    if current_role != "current_signed_runtime" or current_role not in roles:
        raise ValueError("current runtime role is not the current signed runtime")
    evidence_roles = _role_list(
        value.get("sessionmeta_evidence_roles"), roles, "SessionMeta evidence roles"
    )
    hook_roles = _role_list(
        value.get("live_hook_schema_roles"), roles, "live Hook schema roles"
    )
    if set(evidence_roles) != set(roles):
        raise ValueError("SessionMeta evidence roles do not cover the runtime registry")
    if current_role not in hook_roles:
        raise ValueError("current signed runtime is absent from live Hook schema roles")

    evidence = value.get("current_evidence")
    if not isinstance(evidence, dict) or set(evidence) != REQUIRED_CURRENT_EVIDENCE:
        raise ValueError("current runtime evidence set is incomplete")
    for kind, relative in evidence.items():
        if not isinstance(relative, str) or not relative.startswith("probes/"):
            raise ValueError(f"current evidence path {kind} is not repository relative")
        path_value = Path(relative)
        if path_value.is_absolute() or ".." in path_value.parts:
            raise ValueError(f"current evidence path {kind} escapes the repository")
    return value


def runtime_identity(index: dict, role: str | None = None) -> dict:
    selected = role or index["current_runtime_role"]
    try:
        return dict(index["runtime_roles"][selected])
    except KeyError as error:
        raise ValueError(f"unknown semantic runtime role: {selected}") from error


def runtime_pairs(index: dict, role_field: str) -> dict[str, str]:
    roles = index.get(role_field)
    if not isinstance(roles, list):
        raise ValueError(f"runtime evidence index has no {role_field}")
    return {
        index["runtime_roles"][role]["codex_version"]: index["runtime_roles"][role][
            "source_commit"
        ]
        for role in roles
    }


def evidence_path(index: dict, kind: str, repo_root: Path = REPO_ROOT) -> Path:
    try:
        relative = index["current_evidence"][kind]
    except KeyError as error:
        raise ValueError(f"unknown current evidence kind: {kind}") from error
    return repo_root / relative


def verify_current_evidence(index: dict, repo_root: Path = REPO_ROOT) -> list[str]:
    identity = runtime_identity(index)
    failures = []
    for kind in (
        "component_boundaries",
        "native_assignment_seam",
        "lifecycle_sources",
        "mutation_surfaces",
        "appserver_host_control",
    ):
        path = evidence_path(index, kind, repo_root)
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
            failures.append(f"cannot read current {kind} evidence: {error}")
            continue
        if value.get("codex_version") != identity["codex_version"]:
            failures.append(f"current {kind} Codex version disagrees with its semantic role")
        if value.get("source_commit") != identity["source_commit"]:
            failures.append(f"current {kind} source commit disagrees with its semantic role")

    baseline_path = evidence_path(index, "installed_baseline", repo_root)
    try:
        baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        failures.append(f"cannot read current installed baseline: {error}")
    else:
        expected = identity["codex_version"]
        if baseline.get("standalone_cli", {}).get("reported_version") != expected:
            failures.append("standalone CLI version disagrees with current semantic role")
        if baseline.get("codex_app", {}).get("app_server_reported_version") != expected:
            failures.append("App Server version disagrees with current semantic role")
    return failures


def qualification(index_path: Path = DEFAULT_INDEX, repo_root: Path = REPO_ROOT) -> dict:
    index = load_index(index_path)
    identity = runtime_identity(index)
    failures = verify_current_evidence(index, repo_root)
    return {
        "valid": not failures,
        "current_runtime_role": index["current_runtime_role"],
        "codex_version": identity["codex_version"],
        "source_commit": identity["source_commit"],
        "evidence_failures": failures,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--index", type=Path, default=DEFAULT_INDEX)
    parser.add_argument("--repo-root", type=Path, default=REPO_ROOT)
    arguments = parser.parse_args()
    try:
        result = qualification(arguments.index, arguments.repo_root.resolve())
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
        print(json.dumps({"valid": False, "error": str(error)}, separators=(",", ":")))
        return 1
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0 if result["valid"] else 1


if __name__ == "__main__":
    sys.exit(main())
