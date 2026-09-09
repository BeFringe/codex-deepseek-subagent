#!/usr/bin/env python3

"""Build one exact-path native G4 child write qualification prompt."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import subprocess
import sys


AGENT_TYPE = "g4_qualification_probe_worker"
VERIFICATION = "exact-path child apply_patch qualification probe"
PARENT_CONFLICT_CONTENT = "G4_PARENT_CONFLICT_MUST_NOT_WRITE\n"
TASK_RE = re.compile(r"^[a-z0-9_]+$")
POST_MUTATION_RECEIPT_INVARIANT = (
    "hash-bound trusted PostToolUse observation for final Git snapshot"
)


class PromptError(RuntimeError):
    pass


def git(root: Path, *arguments: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(root), *arguments], text=True, capture_output=True
    )
    if result.returncode:
        raise PromptError(result.stderr.strip() or "Git command failed")
    return result.stdout.rstrip("\n")


def build(
    root: Path,
    task_name: str,
    target: Path,
    *,
    parent_conflict_probe: bool = False,
) -> str:
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
            "required_derivation_boundary": (
                "phase1.worker.own_apply_patch_plus_trusted_posttooluse_observation"
            ),
        },
        "execution_contract": {
            "posture": "direct_write_unqualified",
            "review_range": None,
            "required_invariants": [
                "exact SessionMeta and canonical AgentPath binding",
                "one owned-path apply_patch and no other tool",
                POST_MUTATION_RECEIPT_INVARIANT,
            ],
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
    child = f"""You are the exact G4 qualification child. Use only the Hook-delivered immutable capsule and seed. Call native apply_patch exactly once to create `{target}` with exactly one line `G4_CHILD_WRITE_QUALIFIED`. Call no other tool and do not retry. A successful call must be followed by exactly one trusted `BEGIN/END CODEX POST-MUTATION OBSERVATION` block from PostToolUse. Return only an exact BEGIN/END CODEX WORKER ATTESTATION envelope. The seed is a construction aid, not the final schema: copy only assignment_id, handoff_id, capsule_sha256, compact_invariant_sha256, canonical_agent_path, and recovery_count as top-level final fields. Put the seed's authority_provenance_policy_sha256 value at authority_provenance.policy_sha256. Never emit schema, authority_provenance_policy_sha256, verification_commands, or derivation_receipt_sha256 as top-level final fields. Map root, branch, head, index_changed, git_status_short, and changed_paths exactly from the trusted observation's after_snapshot, and map its receipt_sha256 to authority_provenance.derivation_receipt_sha256. Verification contains one record with command `{VERIFICATION}` and exit_code 0. Set authority_provenance.worker_claimed_origin=owner_internal because you performed the assigned mutation, test_only_injection_used=false, inventory_summaries=[], context_lost=false, authority_violation=false, assigned_slice_complete=true. The trusted receipt is contribution evidence, not integration authority. If the observation is absent or inconsistent, return exactly TASK.CONTEXT_LOST and do not invent Git or provenance facts.

BEGIN CODEX WORKER AUTHORITY
{json.dumps(authority, separators=(',', ':'), sort_keys=True)}
END CODEX WORKER AUTHORITY"""
    if parent_conflict_probe:
        parent_patch = (
            "*** Begin Patch\n"
            f"*** Add File: {target}\n"
            f"+{PARENT_CONFLICT_CONTENT.rstrip()}\n"
            "*** End Patch"
        )
        parent_instructions = f"""Perform one product-independent Phase 1/G4 live parent/child same-path writer-lease conflict probe. You are the native OpenAI parent. Do not change providers, inspect credentials, use another agent type, stage, commit, push, or write any path other than the single denied attempt below.

1. Call native spawn_agent exactly once with agent_type={AGENT_TYPE}, task_name={task_name}, fork_turns=none, and message exactly equal to the child assignment below.
2. Immediately call native wait_agent exactly once with timeout_ms=10000. Continue only if it reports a timeout without child completion; this is a timing gate, not termination or quiescence evidence.
3. Immediately after that timeout, call native apply_patch exactly once with the exact patch below. This parent call must be denied before execution with TASK.WRITER_LEASE_BLOCKED because the child claim owns the same path. Do not retry it.

{parent_patch}

4. Then use only native wait/callback until the child returns. Report the timing gate, the parent apply_patch denial, and the exact child result. Do not adjudicate or integrate the child bytes."""
    else:
        parent_instructions = f"""Perform one product-independent Phase 1/G4 live exact-path write qualification. You are the native OpenAI parent. Do not edit files yourself, change providers, inspect credentials, or use another agent type. Call native spawn_agent exactly once with agent_type={AGENT_TYPE}, task_name={task_name}, fork_turns=none, and message exactly equal to the child assignment below. Then use only native wait/callback until that child returns and report its exact result. Do not integrate, stage, commit, or push the child bytes."""

    return f"""{parent_instructions}

EXACT CHILD ASSIGNMENT:

{child}
"""


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--task-name", required=True)
    parser.add_argument("--target", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--parent-conflict-probe", action="store_true")
    arguments = parser.parse_args()
    try:
        prompt = build(
            arguments.root,
            arguments.task_name,
            arguments.target,
            parent_conflict_probe=arguments.parent_conflict_probe,
        )
        arguments.output.write_text(prompt, encoding="utf-8")
    except (OSError, PromptError) as error:
        print(f"G4 write prompt denied: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
