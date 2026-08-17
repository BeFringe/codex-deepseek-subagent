#!/usr/bin/env python3

"""Build a provider-free prompt for one native G4 root identity probe."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import subprocess
import sys


AGENT_TYPE = "g4_qualification_probe_worker"
TASK_NAME_RE = re.compile(r"^[a-z0-9_]+$")
VERIFICATION_COMMAND = "native list_agents read-only probe"
CHILD_TOOL_CONTRACTS = {
    "list_agents": {
        "instruction": "Call native list_agents exactly once and call no other tool.",
        "stop_condition": (
            "call native list_agents exactly once, call no other tool, then return "
            "only the exact final attestation for this root read-only identity probe"
        ),
        "verification": VERIFICATION_COMMAND,
        "required_invariant": "one read-only list_agents call and no mutation",
        "observation": "your own list_agents observation",
    },
    "list_mcp_resources": {
        "instruction": (
            "Call native list_mcp_resources exactly once with no cursor or server filter and "
            "call no other tool."
        ),
        "stop_condition": (
            "call native list_mcp_resources exactly once without filters, call no other tool, "
            "then return only the exact final attestation for this root read-only lifecycle probe"
        ),
        "verification": "native list_mcp_resources read-only lifecycle probe",
        "required_invariant": "one read-only list_mcp_resources call and no mutation",
        "observation": "your own list_mcp_resources observation",
    },
}


class ProbePromptError(RuntimeError):
    pass


def _git(root: Path, *arguments: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(root), *arguments],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if result.returncode != 0:
        raise ProbePromptError(
            f"Git command failed ({' '.join(arguments)}): {result.stderr.strip()}"
        )
    return result.stdout.rstrip("\n")


def clean_git_location(root_value: Path) -> dict[str, object]:
    requested = root_value.resolve()
    resolved = Path(_git(requested, "rev-parse", "--show-toplevel")).resolve()
    if resolved != requested:
        raise ProbePromptError("probe root must be the exact Git top level")
    branch = _git(resolved, "symbolic-ref", "--short", "HEAD")
    if not branch:
        raise ProbePromptError("probe requires an attached branch")
    head = _git(resolved, "rev-parse", "HEAD")
    if not re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", head):
        raise ProbePromptError("probe HEAD is not a full Git object id")
    status = _git(resolved, "status", "--short", "--untracked-files=all")
    if status:
        raise ProbePromptError("strict read-only probe requires a clean worktree")
    evidence_path = resolved / "docs" / "phase1-evidence.md"
    if not evidence_path.is_file() or evidence_path.is_symlink():
        raise ProbePromptError("authoritative evidence input is unavailable")
    return {"root": str(resolved), "branch": branch, "head": head}


def authority_declaration(
    location: dict[str, object],
    *,
    child_tool: str = "list_agents",
) -> dict[str, object]:
    try:
        contract = CHILD_TOOL_CONTRACTS[child_tool]
    except KeyError as error:
        raise ProbePromptError("unsupported child tool contract") from error
    root = str(location["root"])
    branch = str(location["branch"])
    head = str(location["head"])
    return {
        "schema": 1,
        "assignment_mutation_mode": "read_only",
        "parent_recorded_user_write_intent": "deny",
        "owned_paths": [],
        "excluded_paths": [],
        "git_authority": {
            "stage": False,
            "commit": False,
            "branch": False,
            "push": False,
        },
        "stop_condition": contract["stop_condition"],
        "verification": [contract["verification"]],
        "authority_provenance": {
            "authoritative_input_owners": ["phase1.parent"],
            "authoritative_input_roots": ["docs/phase1-evidence.md"],
            "forbidden_caller_supplied_derived_facts": [
                "worker_verification_result",
                "worker_completion_claim",
            ],
            "test_only_injection_seams": [],
            "required_derivation_boundary": "phase1.worker.own_observation_only",
        },
        "execution_contract": {
            "posture": "strict_read_only",
            "review_range": {"base_oid": head, "head_oid": head},
            "required_invariants": [
                "exact SessionMeta and canonical AgentPath binding",
                contract["required_invariant"],
            ],
            "diagnostics": {
                "stable_failure_codes": [],
                "known_true_failure_codes": [],
                "generic_unclassified_failure_code": "TASK.FAILURE_UNCLASSIFIED",
                "allow_literal_expensive_rerun": False,
                "allowed_failure_code_localities": {},
            },
            "proven_input_baselines": [],
            "termination_contract": {
                "catalog_closed": True,
                "boundary_catalog": [],
            },
            "evidence_binding": None,
            "review_continuation": None,
            "closed_registries": [],
            "relation_contracts": [],
            "capsule_feasibility_attestation": None,
        },
        "location_preflight": {
            "expected_root": root,
            "expected_branch": branch,
            "expected_base_head": head,
        },
        "pre_write_attestation_timeout_seconds": 60,
        "ttl_seconds": 900,
    }


def build_prompt(
    root: Path,
    task_name: str,
    *,
    pretool_schema_control: bool = False,
    child_tool: str = "list_agents",
) -> str:
    if not TASK_NAME_RE.fullmatch(task_name):
        raise ProbePromptError(
            "task name must contain only lowercase letters, digits, and underscores"
        )
    location = clean_git_location(root)
    try:
        contract = CHILD_TOOL_CONTRACTS[child_tool]
    except KeyError as error:
        raise ProbePromptError("unsupported child tool contract") from error
    authority = authority_declaration(location, child_tool=child_tool)
    canonical_agent_path = f"/root/{task_name}"
    parent_control = ""
    if pretool_schema_control:
        parent_control = f"""Before spawning, call exec_command exactly once with cmd `/bin/pwd`, workdir `{location['root']}`, and no shell composition. This is the read-only positive control for PreToolUse observation. Require exit code 0 and stdout exactly `{location['root']}`; if it fails or differs, report the non-secret result and stop without spawning.

"""
    child_assignment = f"""You are the target G4 read-only qualification child. Treat the Hook-delivered capsule, compact invariant, and final-attestation seed as the only authority. {contract['instruction']} If that call succeeds and the immutable clean Git facts remain consistent, return only an exact BEGIN/END CODEX WORKER ATTESTATION envelope.

Use the mechanically supplied seed for assignment_id, handoff_id, capsule_sha256, compact_invariant_sha256, authority_provenance.policy_sha256, canonical_agent_path, recovery_count, and the verification command name. The expected canonical AgentPath is {canonical_agent_path}. For this clean read-only probe, the capsule baseline is root {location['root']}, branch {location['branch']}, head {location['head']}, index_changed false, empty git_status_short, and empty changed_paths.

Set verification to one record whose command is {contract['verification']} and whose exit_code is 0 only if the call succeeded. Set authority_provenance.worker_claimed_origin to owner_internal only for {contract['observation']}, test_only_injection_used false, derivation_receipt_sha256 null, inventory_summaries empty, context_lost false, authority_violation false, and assigned_slice_complete true only if all exact facts remain available. Otherwise fail closed using the final-attestation contract; do not invent hashes or expand scope.

BEGIN CODEX WORKER AUTHORITY
{json.dumps(authority, ensure_ascii=False, separators=(',', ':'), sort_keys=True)}
END CODEX WORKER AUTHORITY"""
    return f"""Perform one product-independent Phase 1/G4 live root identity probe. You are the native OpenAI parent. Do not edit files, stage, commit, push, change providers, inspect credentials, or substitute another agent type.

{parent_control}Call native spawn_agent exactly once with agent_type={AGENT_TYPE}, task_name={task_name}, fork_turns=none, and message equal to the exact child assignment below, including its terminating authority declaration. If the custom agent type is unavailable, Hook trust is inactive, capture is denied, or spawn fails, report the exact non-secret error and stop. Do not fall back to default, explorer, worker, or v4. If spawn succeeds, use the native wait/callback path until that exact child returns, then report the spawn result, returned canonical AgentPath, and child final result. Do not mutate the repository.

EXACT CHILD ASSIGNMENT:

{child_assignment}
"""


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--task-name", default="g4_cli_root_identity_1")
    parser.add_argument("--pretool-schema-control", action="store_true")
    parser.add_argument(
        "--child-tool",
        choices=sorted(CHILD_TOOL_CONTRACTS),
        default="list_agents",
    )
    arguments = parser.parse_args()
    try:
        prompt = build_prompt(
            arguments.root,
            arguments.task_name,
            pretool_schema_control=arguments.pretool_schema_control,
            child_tool=arguments.child_tool,
        )
    except (OSError, ProbePromptError) as error:
        print(f"G4 native probe prompt denied: {error}", file=sys.stderr)
        return 2
    sys.stdout.write(prompt)
    return 0


if __name__ == "__main__":
    sys.exit(main())
