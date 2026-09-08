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
REQUIRED_ANCHORS = {
    "app_server_hook_event_enum",
    "additional_context_event_boundary",
    "precompact_output_has_no_context_field",
    "subagentstart_identity_fields",
    "subagentstop_identity_and_transcript_fields",
    "subagentstop_output_has_no_context_field",
    "requested_name_joins_parent_agentpath",
    "spawn_returns_canonical_agentpath",
    "nested_requested_name_contract_test",
    "sessionmeta_precedes_pending_and_flush",
    "resume_preserves_agentpath_contract_test",
    "internal_subagent_resume_restores_stored_metadata_test",
    "v2_root_resume_does_not_reopen_descendants_test",
}
REQUIRED_VERDICT = {
    "hook_schema_source_verified": True,
    "sessionmeta_flush_source_verified": True,
    "canonical_agentpath_source_verified": True,
    "resume_identity_source_verified": True,
    "internal_subagent_resume_identity_supported": True,
    "v2_root_resume_reopens_descendants": False,
    "live_sessionmeta_identity_qualified": False,
    "termination_quiescence_qualified": False,
    "phase1_complete": False,
    "direct_write_qualified": False,
}


def load_contract(path):
    value = json.loads(path.read_text(encoding="utf-8"))
    if value.get("schema") != 1:
        raise ValueError("lifecycle source contract has an invalid schema")
    if not isinstance(value.get("codex_version"), str) or not value["codex_version"]:
        raise ValueError("lifecycle source contract is missing codex_version")
    if GIT_OID.fullmatch(str(value.get("source_commit", ""))) is None:
        raise ValueError("lifecycle source contract has an invalid source_commit")

    anchors = value.get("anchors")
    if not isinstance(anchors, list) or any(not isinstance(item, dict) for item in anchors):
        raise ValueError("lifecycle source anchors must be a list of objects")
    by_id = {item.get("id"): item for item in anchors}
    if len(by_id) != len(anchors) or set(by_id) != REQUIRED_ANCHORS:
        raise ValueError("lifecycle source anchor ids are incomplete or duplicated")
    for anchor in anchors:
        if not all(
            isinstance(anchor.get(key), str) and anchor[key]
            for key in ("path", "contains")
        ):
            raise ValueError(f"lifecycle source anchor {anchor.get('id')} is invalid")

    verdict = value.get("verdict")
    if not isinstance(verdict, dict):
        raise ValueError("lifecycle source contract is missing its verdict")
    for key, expected in REQUIRED_VERDICT.items():
        if verdict.get(key) != expected:
            raise ValueError(f"lifecycle source verdict cannot promote {key}")
    if not isinstance(verdict.get("blocker"), str) or not verdict["blocker"]:
        raise ValueError("lifecycle source verdict is missing its blocker")
    return value


def _git_identity(source_root):
    try:
        requested = source_root.resolve(strict=True)
    except OSError as error:
        return None, None, [f"cannot resolve Codex source root: {error}"]

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
            failures.append(f"cannot resolve Codex source {label}")
        else:
            values[label] = result.stdout.strip()
    root = values.get("root")
    if root is not None and Path(root).resolve() != requested:
        failures.append("Codex source path is not the exact Git top level")
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
            text = (root / anchor["path"]).read_text(encoding="utf-8")
        except OSError as error:
            failures.append(f"{anchor['id']}: cannot read {anchor['path']}: {error}")
            continue
        if anchor["contains"] not in text:
            failures.append(f"source anchor drifted: {anchor['id']}")
    return head, failures


def qualification(contract):
    return dict(contract["verdict"])


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--contract",
        type=Path,
    )
    parser.add_argument("--release-index", type=Path, default=DEFAULT_INDEX)
    parser.add_argument("--codex-source", type=Path, required=True)
    parser.add_argument("--require-live-identity", action="store_true")
    args = parser.parse_args()

    try:
        index = load_index(args.release_index)
        identity = runtime_identity(index)
        contract_path = args.contract or evidence_path(index, "lifecycle_sources")
        contract = load_contract(contract_path)
        if any(contract[key] != identity[key] for key in ("codex_version", "source_commit")):
            raise ValueError(
                "lifecycle source identity disagrees with the current runtime role"
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
    if args.require_live_identity and not result["live_sessionmeta_identity_qualified"]:
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
