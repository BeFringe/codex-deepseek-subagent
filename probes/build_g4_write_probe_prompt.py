#!/usr/bin/env python3

"""Build one exact-path native G4 child write qualification prompt."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys


AGENT_TYPE = "g4_qualification_probe_worker"
VERIFICATION = "exact-path child apply_patch qualification probe"
CONTENT = "G4_CHILD_WRITE_QUALIFIED\n"
TASK_RE = re.compile(r"^[a-z0-9_]+$")


class PromptError(RuntimeError):
    pass


def git(root: Path, *arguments: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(root), *arguments], text=True, capture_output=True
    )
    if result.returncode:
        raise PromptError(result.stderr.strip() or "Git command failed")
    return result.stdout.rstrip("\n")


def build(root: Path, task_name: str, target: Path) -> str:
    root = root.resolve()
    if not TASK_RE.fullmatch(task_name):
        raise PromptError("task name is not canonical")
    if root.parent != Path("/private/tmp") or Path(git(root, "rev-parse", "--show-toplevel")).resolve() != root:
        raise PromptError("root is not an exact temporary Git top level")
    if target.parent.resolve() != root or target.resolve(strict=False) != target or target.exists():
        raise PromptError("target is not one absent canonical direct root child")
    branch = git(root, "symbolic-ref", "--short", "HEAD")
    head = git(root, "rev-parse", "HEAD")
    if git(root, "status", "--short", "--untracked-files=all"):
        raise PromptError("root is not clean")
    evidence = root / "docs" / "phase1-evidence.md"
    if not evidence.is_file() or evidence.is_symlink():
        raise PromptError("authoritative input is unavailable")
    relative = target.relative_to(root).as_posix()
    authority = {
        "schema": 1,
        "assignment_mutation_mode": "write",
        "parent_recorded_user_write_intent": "allow",
        "owned_paths": [relative],
        "excluded_paths": [],
        "git_authority": {"stage": False, "commit": False, "branch": False, "push": False},
        "stop_condition": "perform one exact owned-path apply_patch and return only the final attestation",
        "verification": [VERIFICATION],
        "authority_provenance": {
            "authoritative_input_owners": ["phase1.parent"],
            "authoritative_input_roots": ["docs/phase1-evidence.md"],
            "forbidden_caller_supplied_derived_facts": ["worker_completion_claim"],
            "test_only_injection_seams": [],
            "required_derivation_boundary": "phase1.worker.own_apply_patch_observation_only",
        },
        "execution_contract": {
            "posture": "direct_write_unqualified",
            "review_range": None,
            "required_invariants": ["exact SessionMeta and canonical AgentPath binding", "one owned-path apply_patch and no other tool"],
            "diagnostics": {"stable_failure_codes": [], "known_true_failure_codes": [], "generic_unclassified_failure_code": "TASK.FAILURE_UNCLASSIFIED", "allow_literal_expensive_rerun": False, "allowed_failure_code_localities": {}},
            "proven_input_baselines": [],
            "termination_contract": {"catalog_closed": True, "boundary_catalog": []},
            "evidence_binding": None,
            "review_continuation": None,
            "closed_registries": [],
            "relation_contracts": [],
            "capsule_feasibility_attestation": {
                "parent_owner_id": "phase1.parent",
                "exact_claimed_invariant": "one exact temporary owned-path write closes within one tool call",
                "counterexample_probe": {"probe_id": "write-ceiling-negative-space", "probe_input_sha256": "1" * 64, "executed": True, "counterexample_found": False, "evidence_sha256": "2" * 64},
                "bounded_completion": {
                    "completion_condition": "one exact owned-path apply_patch",
                    "work_budget": {"unit": "tool-call", "cardinality_domain": "owned-path", "limit": 1},
                    "proposed_mechanism": "exact Hook ceiling plus writer lease",
                    "mechanism_measurement": {"unit": "tool-call", "cardinality_domain": "owned-path", "required_lower_bound": 1},
                    "scale_evidence": {"basis": "proven_monotonicity", "witness_input_sha256": None, "evidence_sha256": "3" * 64},
                    "equivalence_compression": None,
                    "mechanism_satisfies": True,
                    "evidence_sha256": "4" * 64,
                },
                "unresolved_assumptions": [],
                "owner_decision": "dispatch",
            },
        },
        "location_preflight": {"expected_root": str(root), "expected_branch": branch, "expected_base_head": head},
        "pre_write_attestation_timeout_seconds": 60,
        "ttl_seconds": 900,
    }
    digest = hashlib.sha256(CONTENT.encode()).hexdigest()
    final_snapshot = {
        "root": str(root), "branch": branch, "head": head, "index_changed": False,
        "git_status_short": f"?? {relative}",
        "changed_paths": [{"path": relative, "kind": "file", "sha256": digest}],
    }
    child = f"""You are the exact G4 qualification child. Use only the Hook-delivered immutable capsule and seed. Call native apply_patch exactly once to create `{target}` with exactly one line `G4_CHILD_WRITE_QUALIFIED`. Call no other tool and do not retry. If apply_patch succeeds, return only an exact BEGIN/END CODEX WORKER ATTESTATION envelope. Map seed keys exactly as instructed by the capsule contract. Use this exact final Git snapshot: {json.dumps(final_snapshot, separators=(',', ':'), sort_keys=True)}. Verification contains one record with command `{VERIFICATION}` and exit_code 0. Set authority_provenance.worker_claimed_origin=owner_internal, test_only_injection_used=false, derivation_receipt_sha256=null, inventory_summaries=[], context_lost=false, authority_violation=false, assigned_slice_complete=true. If any fact differs, fail closed and do not invent values.

BEGIN CODEX WORKER AUTHORITY
{json.dumps(authority, separators=(',', ':'), sort_keys=True)}
END CODEX WORKER AUTHORITY"""
    return f"""Perform one product-independent Phase 1/G4 live exact-path write qualification. You are the native OpenAI parent. Do not edit files yourself, change providers, inspect credentials, or use another agent type. Call native spawn_agent exactly once with agent_type={AGENT_TYPE}, task_name={task_name}, fork_turns=none, and message exactly equal to the child assignment below. Then use only native wait/callback until that child returns and report its exact result. Do not integrate, stage, commit, or push the child bytes.

EXACT CHILD ASSIGNMENT:

{child}
"""


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--task-name", required=True)
    parser.add_argument("--target", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args()
    try:
        prompt = build(arguments.root, arguments.task_name, arguments.target)
        arguments.output.write_text(prompt, encoding="utf-8")
    except (OSError, PromptError) as error:
        print(f"G4 write prompt denied: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
